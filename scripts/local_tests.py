"""Run local integration tests against a private MCP from the SAME source tree."""
import os
import subprocess
import sys
from eval.robustness import start_private_mcp


if __name__=='__main__':
    process,url=start_private_mcp()
    try:
        result=subprocess.run([sys.executable,'-m','pytest',*sys.argv[1:]],
            env={**os.environ,'MCP_URL':url,'RUN_DB_TESTS':'1','RUN_MCP_TESTS':'1'})
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
    raise SystemExit(result.returncode)
