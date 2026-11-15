"""배포 설정 검사: Vercel 은 pyproject.toml 의 dependencies 를 우선 설치한다."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_dependencies_match_requirements():
    reqs = [line.split("#")[0].strip() for line in (ROOT / "requirements.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    assert sorted(deps) == sorted(reqs)


def test_vercel_entrypoint_points_to_app():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert cfg["tool"]["vercel"]["entrypoint"] == "web.main:app"
