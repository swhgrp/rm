"""
Main entry point for Integration Hub application
Run with: python -m integration_hub
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "integration_hub.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
