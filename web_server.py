#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  企业级多币种资金池管理系统 - Web服务器")
    print("=" * 60)
    print("")
    print("  访问地址: http://localhost:8000")
    print("  API文档: http://localhost:8000/docs")
    print("")
    print("  按 Ctrl+C 停止服务器")
    print("")
    print("=" * 60)
    print("")
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
