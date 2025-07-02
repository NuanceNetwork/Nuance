import asyncio

from nuance.constitution import constitution_store


async def test_get_nuance_prompt():
    prompt = await constitution_store.get_nuance_prompt()
    print(prompt)

if __name__ == "__main__":
    asyncio.run(test_get_nuance_prompt())