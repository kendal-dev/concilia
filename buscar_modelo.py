import os, asyncio
import tetherto.qvac_sdk as q
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = q.Client(
        sdk_dir=os.environ.get("QVAC_SDK_DIR"),
        bare_path=os.environ.get("QVAC_BARE_PATH")
    )
    try:
        # FIX: Entrar al contexto asíncrono para despertar la conexión IPC
        async with client:
            res = q.model_registry_list(client.transport)
            if asyncio.iscoroutine(res):
                res = await res
            
            for m in res:
                if 'ocr' in str(getattr(m, 'id', '')).lower():
                    print(f"ID EXACTO: {m.id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())