from nuance.constitution import constitution
import asyncio

async def test_get_nuance_prompt():
    prompt = await constitution.get_nuance_prompt()
    print(prompt)

if __name__ == "__main__":
    asyncio.run(test_get_nuance_prompt())