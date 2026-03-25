# Database

## Current bootstrap

The backend now includes an initial SQLAlchemy model set for:

- organizations
- marketplace credentials
- campaigns
- campaign products
- campaign daily metrics
- bid changes
- campaign comments

Default development database:

- `sqlite:///./ozon_ads_dev.db`

Override with:

- `DATABASE_URL`

## Temporary bootstrap

Before Alembic is wired in, tables can be created with:

```bash
python -c "import sys; sys.path.insert(0, 'backend'); from app.db.bootstrap import create_all; create_all()"
```

This is a temporary setup step for early migration work. Proper migrations will be added next.
