# scheduling-demo-form (Web Service)

This repo supports Render Web Service deployment with form submission collection API.

## Local Run

```bash
python3 CODE/run_scheduling_demo.py --host 0.0.0.0 --port 8000
```

## Render

- Runtime: Python
- Build Command: `echo "no build required"`
- Start Command: `python3 CODE/run_scheduling_demo.py --host 0.0.0.0 --port $PORT`

API:
- `POST /api/submissions`

Data path (in service container):
- `CODE/submissions/`
