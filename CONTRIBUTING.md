# Contributing to Nexus

First off, thank you for considering contributing to Nexus! This platform is being built in public, and community feedback and contributions are exactly what will make it great.

## Setting Up Your Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/Vishwajeet2005/Nexus--AI-NPC-backend.git
   cd Nexus--AI-NPC-backend
   ```

2. Set up your environment variables:
   ```bash
   cp env.example .env
   ```
   *(Update `.env` to point to `postgres` and `redis` instead of `localhost` if you plan to run everything inside Docker).*

3. Start the stack:
   ```bash
   make up
   # or: docker compose up -d
   ```

4. Run the database migrations:
   ```bash
   make migrate
   # or: docker compose exec api alembic upgrade head
   ```

## Pull Request Process

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Ensure the test suite passes (run `pytest`).
4. Format your code with `ruff format .` and lint with `ruff check .` or just `make format` and `make lint`.
5. Issue that pull request!

## Code Style

We use `ruff` for all Python formatting and linting. Please ensure you conform to the settings defined in `pyproject.toml`.

Thank you for helping build the future of AI-native gaming!
