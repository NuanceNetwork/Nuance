from nuance.social.platforms.twitter import TwitterPlatform
import asyncio

async def test_get_all_quotes():
    platform = TwitterPlatform()
    quotes = await platform.get_all_quotes("1906741029606424576")
    print(quotes)

if __name__ == "__main__":
    asyncio.run(test_get_all_quotes())
