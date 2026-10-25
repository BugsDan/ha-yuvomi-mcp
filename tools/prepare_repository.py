"""Create a clean review ZIP for a future new repository; never initialize or push Git."""

from build_release import archive
from check_repository import validate
from repository_files import public_files


def prepare(output_dir=None):
    errors = validate()
    if errors:
        raise ValueError("Publication check failed; run tools/check_repository.py")
    return archive("ha-yuvomi-mcp-publication.zip", public_files(), output_dir=output_dir)


if __name__ == "__main__":
    target, digest = prepare()
    print(f"{digest}  {target.name}")
