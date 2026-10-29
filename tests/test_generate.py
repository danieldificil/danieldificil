import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate  # noqa: E402

NOW = datetime(2026, 10, 28, 17, 40, tzinfo=timezone.utc)
HEIGHT = 530
ROOT = Path(__file__).resolve().parent.parent
CLOCK = r"\d{2}:\d{2}"


def sector(name, machine, events, **extra):
    data = {
        "machine": machine,
        "sector": name,
        "generated_on": "2026-10-28",
        "window_days": 7,
        "agents": ["franky", "chopper", "korosensei", "nami", "robin", "vegapunk"],
        "active_clients": 0,
        "metrics": {"tasks": 41, "prs_fixed": 23, "qa_catches": 3, "pre_review_blocks": 2},
        "last_action": {"agent": "franky", "on": "2026-10-28"},
        "events": events,
    }
    data.update(extra)
    return data


def event(on, agent, kind, n=1):
    return {"on": on, "agent": agent, "type": kind, "n": n}


def sample():
    return {
        "Engineering": sector("Engineering", "machine-1", [
            event("2026-10-28", "franky", "franky_fixed", 3),
            event("2026-10-28", "chopper", "qa"),
            event("2026-10-28", "nami", "routine"),
        ]),
        "DificilTech": sector("DificilTech", "machine-2", [
            event("2026-10-28", "robin", "task"),
            event("2026-10-27", "vegapunk", "delivery"),
        ], active_clients=1),
    }


def profile_cfg():
    return json.loads((ROOT / "config" / "profile.json").read_text(encoding="utf-8"))


class PhraseTest(unittest.TestCase):
    def test_phrase_for_each_type(self):
        cases = {
            ("franky", "franky_fixed", 3): "franky fixed 3 review comments",
            ("chopper", "qa", 1): "chopper caught an issue in QA",
            ("vegapunk", "delivery", 1): "vegapunk shipped a feature",
            ("robin", "task", 1): "robin completed a task",
            ("korosensei", "routine", 1): "koro ran a scheduled routine",
        }
        for (agent, kind, n), expected in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(generate.phrase(event("2026-10-28", agent, kind, n)), expected)

    def test_phrase_singular_review_comment(self):
        self.assertEqual(generate.phrase(event("2026-10-28", "franky", "franky_fixed", 1)),
                         "franky fixed 1 review comment")
        self.assertEqual(generate.phrase(event("2026-10-28", "franky", "franky_fixed", 11)),
                         "franky fixed 11 review comments")

    def test_phrase_franky_with_zero_comments_is_none(self):
        self.assertIsNone(generate.phrase(event("2026-10-28", "franky", "franky_fixed", 0)))

    def test_phrase_unknown_type_or_agent_is_none(self):
        stranger = event("2026-10-28", "intruder", "task")
        self.assertIsNone(generate.phrase(stranger))
        self.assertIsNone(generate.phrase(event("2026-10-28", "franky", "opened_pr")))

        sectors = sample()
        sectors["Engineering"]["events"].append(stranger)
        self.assertNotIn("intruder", generate.ships_log(sectors, HEIGHT))


class StatusTest(unittest.TestCase):
    def test_status_on_duty_up_to_one_day_then_low_orbit_and_awaiting(self):
        self.assertEqual(generate.status(None, NOW), ("awaiting", None))
        self.assertEqual(generate.status("junk", NOW), ("awaiting", None))
        self.assertEqual(generate.status("2026-10-28", NOW), ("on_duty", 0))
        self.assertEqual(generate.status("2026-10-27", NOW), ("on_duty", 1))
        self.assertEqual(generate.status("2026-10-26", NOW), ("low_orbit", 2))

    def test_status_counts_days_in_sao_paulo(self):
        early_utc = datetime(2026, 10, 29, 2, 0, tzinfo=timezone.utc)
        self.assertEqual(generate.status("2026-10-27", early_utc), ("on_duty", 1))

    def test_status_rejects_a_full_datetime(self):
        self.assertEqual(generate.status("2026-10-28T11:21:12-03:00", NOW), ("awaiting", None))


class LoadTest(unittest.TestCase):
    def test_load_missing_or_corrupt_file_becomes_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "machine-2.json").write_text("{corrupt", encoding="utf-8")
            sectors = generate.load(folder)
        self.assertEqual(sectors, {"Engineering": None, "DificilTech": None})
        self.assertIn("AWAITING FIRST CONTACT", generate.mission_control(sectors, NOW))

    def test_load_indexes_by_sector(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "machine-1.json").write_text(json.dumps(sample()["Engineering"]), encoding="utf-8")
            sectors = generate.load(folder)
        self.assertEqual(sectors["Engineering"]["machine"], "machine-1")
        self.assertIsNone(sectors["DificilTech"])


class ShipsLogTest(unittest.TestCase):
    def test_feed_shows_only_the_day(self):
        sectors = {"Engineering": sector("Engineering", "machine-1", [
            event("2026-10-27", "franky", "franky_fixed", 3),
        ]), "DificilTech": None}
        self.assertIn(">27/10<", generate.ships_log(sectors, HEIGHT))

    def test_feed_skips_event_with_a_full_datetime(self):
        sectors = {"Engineering": sector("Engineering", "machine-1", [
            event("2026-10-28T01:32:00+00:00", "franky", "franky_fixed", 3),
        ]), "DificilTech": None}
        self.assertEqual(generate.log_events(sectors), [])

    def test_empty_feed_shows_crew_at_rest(self):
        zeroed = dict.fromkeys(generate.METRICS, 0)
        sectors = {
            "Engineering": sector("Engineering", "machine-1", [], metrics=zeroed, last_action=None),
            "DificilTech": None,
        }
        self.assertIn("crew at rest", generate.ships_log(sectors, HEIGHT))
        mc = generate.mission_control(sectors, NOW)
        for key in generate.METRICS:
            self.assertIn(f'data-metric="{key}">0<', mc)

    def test_log_sorts_by_day_and_keeps_each_sector_order_within_a_day(self):
        eng = [event("2026-10-28", "robin", "task", 1), event("2026-10-28", "franky", "franky_fixed", 2),
               event("2026-10-26", "robin", "task", 3)]
        dt = [event("2026-10-28", "nami", "routine", 4), event("2026-10-27", "nami", "routine", 5),
              event("2026-10-27", "chopper", "qa", 6)]
        events = generate.log_events({
            "Engineering": sector("Engineering", "machine-1", eng),
            "DificilTech": sector("DificilTech", "machine-2", dt),
        })
        self.assertEqual([e["n"] for _, e in events], [1, 2, 4, 5, 6, 3])

    def test_log_cap_of_12_keeps_the_newest(self):
        eng = [event(f"2026-10-{d:02d}", "robin", "task") for d in range(10, 20)]
        dt = [event(f"2026-10-{d:02d}", "nami", "routine") for d in range(20, 28)]
        events = generate.log_events({
            "Engineering": sector("Engineering", "machine-1", eng),
            "DificilTech": sector("DificilTech", "machine-2", dt),
        })
        self.assertEqual(len(events), 12)
        self.assertEqual(events[0][1]["on"], "2026-10-27")
        self.assertEqual(events[-1][1]["on"], "2026-10-16")


class SvgTest(unittest.TestCase):
    def everything(self, sectors):
        cfg = profile_cfg()
        return [
            generate.profile(cfg),
            generate.mission_control(sectors, NOW),
            generate.ships_log(sectors, HEIGHT),
            generate.button("LinkedIn"),
            generate.button("dificiltech.com"),
        ]

    def test_svgs_are_valid_xml(self):
        for svg in self.everything(sample()) + self.everything({"Engineering": None, "DificilTech": None}):
            ET.fromstring(svg)

    def test_svg_text_only_has_known_pieces(self):
        cfg = profile_cfg()
        known = [
            "MISSION CONTROL", "TELEMETRY LAST DAYS", "SECTOR", "ON DUTY", "LOW ORBIT",
            "NO SIGNAL", "AWAITING FIRST CONTACT", "this sector hasn't transmitted yet",
            "machine transmitted last transmission days ago", "active client clients", "AI CREW agent agents",
            "TASKS in days", "PRs FIXED by", "BUGS CAUGHT IN QA", "BLOCKED IN PRE-REVIEW before push",
            "LAST ACTION", "hermes AI agent crew across two ships", "SHIP'S LOG", "LIVE",
            "crew at rest", "no actions logged in the window", "COMMANDER PROFILE",
            "FLIGHT PATH", "today", "new", "open channel", "LinkedIn", "dificiltech.com", "comment",
            cfg["name"], cfg["subtitle"], cfg["status"], *(r["tech"] for r in cfg["flight_path"]),
            *generate.PHRASES.values(), *generate.SECTORS, *generate.CREW, *generate.NICKNAMES.values(),
        ]
        word = re.compile(r"[^\W\d_]+")
        vocabulary = {w.lower() for text in known for w in word.findall(text)}
        for svg in self.everything(sample()) + self.everything({"Engineering": None, "DificilTech": None}):
            for node in ET.fromstring(svg).iter():
                if node.tag.split("}")[-1] not in ("text", "tspan"):
                    continue
                for w in word.findall(node.text or ""):
                    self.assertIn(w.lower(), vocabulary, node.text)

    def test_sector_on_duty_shows_transmission_day(self):
        sectors = sample()
        sectors["Engineering"]["generated_on"] = "2026-10-27"
        mc = generate.mission_control(sectors, NOW)
        self.assertIn("● ON DUTY", mc)
        self.assertIn("machine 1 · transmitted 27/10", mc)
        self.assertIn("franky · 28/10", mc)
        self.assertNotIn("ago", mc)

    def test_sector_in_low_orbit_shows_days_since_transmission(self):
        sectors = sample()
        sectors["Engineering"]["generated_on"] = "2026-10-25"
        mc = generate.mission_control(sectors, NOW)
        self.assertIn("◌ LOW ORBIT", mc)
        self.assertIn("machine 1 · last transmission 3 days ago", mc)

    def test_sector_titles_and_active_clients(self):
        mc = generate.mission_control(sample(), NOW)
        self.assertIn("SECTOR ENGINEERING", mc)
        self.assertIn("SECTOR DIFICILTECH", mc)
        self.assertIn("machine 2 · transmitted 28/10 · 1 active client", mc)

    def test_no_svg_shows_a_clock_time(self):
        for sectors in (sample(), {"Engineering": None, "DificilTech": None}):
            for svg in self.everything(sectors):
                self.assertNotRegex(svg, CLOCK)

    def test_renders_on_the_same_day_with_the_same_data_are_identical(self):
        cfg = (ROOT / "config" / "profile.json").read_bytes()
        outputs = []
        start = datetime(2026, 10, 28, 0, 0, tzinfo=generate.SAO_PAULO)
        for now in (start, start + timedelta(hours=14, minutes=40), start + timedelta(hours=23, minutes=59)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "config").mkdir()
                (root / "config" / "profile.json").write_bytes(cfg)
                (root / "data").mkdir()
                for data in sample().values():
                    (root / "data" / f"{data['machine']}.json").write_text(json.dumps(data), encoding="utf-8")
                generate.main(root, now)
                outputs.append({n: (root / "svg" / n).read_bytes() for n in ("mission-control.svg", "log.svg")})
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_data_is_escaped(self):
        sectors = sample()
        sectors["Engineering"]["machine"] = "<script>"
        ET.fromstring(generate.mission_control(sectors, NOW))

    def test_main_writes_the_five_svgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "profile.json").write_bytes((ROOT / "config" / "profile.json").read_bytes())
            self.assertEqual(generate.main(root, NOW), 0)
            written = sorted(p.name for p in (root / "svg").iterdir())
        self.assertEqual(written, sorted(generate.OUTPUTS))


if __name__ == "__main__":
    unittest.main()
