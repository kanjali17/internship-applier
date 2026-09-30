"""Loads your preferences, profile, stories and writing rules. One place, so every script agrees."""
import json, os, pathlib, tomllib, functools

ROOT = pathlib.Path(__file__).resolve().parent.parent

class SetupError(SystemExit):
    pass

def _need(path, hint):
    p = ROOT / path
    if not p.exists():
        raise SetupError(f"Missing {path}. {hint}")
    return p

@functools.lru_cache(None)
def prefs():
    return tomllib.loads(_need("config/preferences.toml", "It ships with the repo; restore it from git.").read_text())

@functools.lru_cache(None)
def writing():
    return tomllib.loads(_need("config/writing.toml", "It ships with the repo; restore it from git.").read_text())

# AUTOPILOT_EXAMPLE=1 runs everything against the example templates (used by the tests).
EXAMPLE = os.environ.get("AUTOPILOT_EXAMPLE") == "1"

@functools.lru_cache(None)
def profile():
    if EXAMPLE:
        return json.loads((ROOT / "templates/profile.example.json").read_text())
    return json.loads(_need("data/profile.json", "Run `python3 autopilot.py init`, then fill it in.").read_text())

@functools.lru_cache(None)
def stories():
    if EXAMPLE:
        return json.loads((ROOT / "templates/stories.example.json").read_text())["stories"]
    return json.loads(_need("data/stories.json", "Run `python3 autopilot.py init`, then add your projects.").read_text())["stories"]

def tracks():
    return {t["name"]: t for t in prefs()["tracks"]}

def resume_for(track):
    return tracks()[track]["resume"]

def statuses():
    return prefs()["tracker"]["statuses"]
