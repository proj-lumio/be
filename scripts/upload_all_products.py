"""Create companies for products 3-20 and upload their mock contracts via API."""

import asyncio
import aiohttp
import os
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"
MOCK_DIR = Path(__file__).parent.parent / "mock_data"

PRODUCTS = [
    {"folder": "prodotto3", "name": "VaultCRM", "industry": "CRM e gestione clienti"},
    {"folder": "prodotto4", "name": "ShieldNet", "industry": "Cybersecurity e monitoraggio"},
    {"folder": "prodotto5", "name": "InvoiceFlow", "industry": "Fatturazione elettronica"},
    {"folder": "prodotto6", "name": "PeopleHub", "industry": "Gestione risorse umane"},
    {"folder": "prodotto7", "name": "TrackLine", "industry": "Logistica e supply chain"},
    {"folder": "prodotto8", "name": "InsightBI", "industry": "Business intelligence e analytics"},
    {"folder": "prodotto9", "name": "DocVault", "industry": "Gestione documentale"},
    {"folder": "prodotto10", "name": "SprintDesk", "industry": "Project management"},
    {"folder": "prodotto11", "name": "ShopEngine", "industry": "E-commerce"},
    {"folder": "prodotto12", "name": "SensIoT", "industry": "IoT e monitoraggio industriale"},
    {"folder": "prodotto13", "name": "LexComply", "industry": "Legal tech e compliance"},
    {"folder": "prodotto14", "name": "MediConnect", "industry": "Telemedicina e sanità digitale"},
    {"folder": "prodotto15", "name": "LearnSphere", "industry": "EdTech e formazione"},
    {"folder": "prodotto16", "name": "PayGate", "industry": "FinTech e pagamenti"},
    {"folder": "prodotto17", "name": "CampaignForge", "industry": "Marketing automation"},
    {"folder": "prodotto18", "name": "CloudNest", "industry": "Cloud storage e backup"},
    {"folder": "prodotto19", "name": "GreenLens", "industry": "Sostenibilità e reporting ESG"},
    {"folder": "prodotto20", "name": "HelpStream", "industry": "Customer support e ticketing"},
]


async def login(session: aiohttp.ClientSession) -> str:
    async with session.post(f"{BASE_URL}/auth/login", json={
        "email": "sloth@gmail.com", "password": "Sloth@123"
    }) as r:
        data = await r.json()
        return data["access_token"]


async def create_company(session: aiohttp.ClientSession, token: str, product: dict) -> str | None:
    headers = {"Authorization": f"Bearer {token}"}
    async with session.post(f"{BASE_URL}/companies", json={
        "name": product["name"],
        "industry": product["industry"],
    }, headers=headers) as r:
        if r.status != 200 and r.status != 201:
            text = await r.text()
            print(f"  ERROR creating {product['name']}: {r.status} {text}")
            return None
        data = await r.json()
        cid = data["id"]
        print(f"  Created {product['name']} -> {cid}")
        return cid


async def upload_contracts(session: aiohttp.ClientSession, token: str, company_id: str, product: dict):
    headers = {"Authorization": f"Bearer {token}"}
    folder = MOCK_DIR / product["folder"]
    files = sorted(folder.glob("*.docx"))
    if not files:
        print(f"  WARNING: No .docx files in {folder}")
        return

    # Upload in batches of 5 to avoid overwhelming the server
    batch_size = 5
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        data = aiohttp.FormData()
        for f in batch:
            data.add_field("files", open(f, "rb"), filename=f.name, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

        async with session.post(
            f"{BASE_URL}/companies/{company_id}/documents/multipart",
            data=data,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as r:
            if r.status == 200 or r.status == 201:
                resp = await r.json()
                count = len(resp) if isinstance(resp, list) else resp.get("uploaded", "?")
                print(f"  {product['name']}: uploaded batch {i//batch_size+1} ({len(batch)} files)")
            else:
                text = await r.text()
                print(f"  ERROR uploading {product['name']} batch: {r.status} {text[:200]}")


async def process_product(session: aiohttp.ClientSession, token: str, product: dict):
    cid = await create_company(session, token, product)
    if cid:
        await upload_contracts(session, token, cid, product)
    return cid


async def main():
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        token = await login(session)
        print(f"Logged in. Processing {len(PRODUCTS)} products...\n")

        # Process 3 products at a time to avoid overwhelming the server
        semaphore = asyncio.Semaphore(3)

        async def limited(product):
            async with semaphore:
                return await process_product(session, token, product)

        results = await asyncio.gather(*[limited(p) for p in PRODUCTS])

        created = sum(1 for r in results if r)
        print(f"\nDone! Created {created}/{len(PRODUCTS)} companies with contracts uploaded.")
        print("Documents are being processed in background by the ingestion pipeline.")


if __name__ == "__main__":
    asyncio.run(main())
