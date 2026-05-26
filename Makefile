install-skill:
	mkdir -p ~/.claude/skills/strong-opx
	cp skills/strong-opx/SKILL.md ~/.claude/skills/strong-opx/SKILL.md

lint:
	black . --check --quiet
	isort . --check-only

lint-fix:
	black .
	isort .

test:
	pytest .

test-coverage:
	coverage run --source=strong_opx -m pytest
	coverage report
