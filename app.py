import time
import traceback

from services import build_audit_result, build_user_profile
from ui import build_page_html
from utils import (
    log_timing,
)

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    FastAPI = None
    Request = None
    HTMLResponse = None
    JSONResponse = None

def calculate_daily_wh(quantity, watts, hours, duty_percentage):
    """Calculate daily Wh from UI-style duty percentage values."""
    return quantity * watts * hours * (duty_percentage / 100.0)


if FastAPI is not None:
    app = FastAPI(title="Van Energy Budget")

    @app.get("/", response_class=HTMLResponse)
    async def home():
        return HTMLResponse(build_page_html())


    @app.get("/health")
    async def health():
        return {"status": "ok"}


    @app.post("/generate")
    async def generate(request: Request):
        request_start = time.perf_counter()
        log_timing("request received", request_start)
        try:
            payload = await request.json()
            user_profile = build_user_profile(payload)
            result = build_audit_result(user_profile, request_start_time=request_start)
            log_timing("response ready", request_start, total_duration_ms=f"{(time.perf_counter() - request_start) * 1000:.1f}")
            log_timing("total request duration", request_start)
            return JSONResponse(result)
        except ValueError as e:
            print("ENERGY BUDGET ERROR:", e)
            log_timing("response ready", request_start, total_duration_ms=f"{(time.perf_counter() - request_start) * 1000:.1f}", status="invalid_input")
            log_timing("total request duration", request_start, status="invalid_input")
            return JSONResponse(
                {
                    "error": str(e),
                    "raw_ai_response": "",
                },
                status_code=400,
            )
        except Exception as e:
            print("ENERGY BUDGET ERROR:", e)
            log_timing("response ready", request_start, total_duration_ms=f"{(time.perf_counter() - request_start) * 1000:.1f}", status="error")
            log_timing("total request duration", request_start, status="error")
            traceback.print_exc()
            return JSONResponse(
                {
                    "error": str(e),
                    "raw_ai_response": getattr(e, "raw_response_text", ""),
                },
                status_code=500,
            )

else:
    app = None


if __name__ == "__main__":
    if app is None:
        raise SystemExit("FastAPI and uvicorn are not installed. Install them with: pip install fastapi uvicorn")

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
