from nuance.social.discovery.twitter import _tweet_to_interaction
from nuance import models
import json

def test_quote_to_interaction():
    quote = json.loads("""{
        "user": {
            "id": "1775173168317243392",
            "url": "https://x.com/hopecore11",
            "name": "hopecore",
            "username": "hopecore11",
            "created_at": "Tue Apr 02 14:47:28 +0000 2024",
            "description": "",
            "favourites_count": 29,
            "followers_count": 1,
            "listed_count": 0,
            "media_count": 0,
            "profile_image_url": "https://pbs.twimg.com/profile_images/1831234128919842816/11Y5A-Al_normal.jpg",
            "profile_banner_url": null,
            "statuses_count": 31,
            "verified": false,
            "is_blue_verified": false,
            "entities": {
                "description": {
                    "urls": []
                },
                "url": null
            },
            "can_dm": false,
            "can_media_tag": true,
            "location": "",
            "pinned_tweet_ids": []
        },
        "id": "1911631687169311110",
        "text": "LOL",
        "reply_count": 0,
        "retweet_count": 0,
        "like_count": 0,
        "quote_count": 0,
        "bookmark_count": 0,
        "url": "https://x.com/hopecore11/status/1911631687169311110",
        "created_at": "Mon Apr 14 04:04:45 +0000 2025",
        "media": [],
        "is_quote_tweet": true,
        "is_retweet": false,
        "lang": "qst",
        "conversation_id": "1911631687169311110",
        "in_reply_to_screen_name": null,
        "in_reply_to_status_id": null,
        "in_reply_to_user_id": null,
        "quoted_status_id": "1910612683029962794",
        "quote": {
            "user": {
                "id": "1906741029606424576",
                "url": "https://x.com/ralatha_",
                "name": "Zathalan",
                "username": "ralatha_",
                "created_at": "Mon Mar 31 16:11:09 +0000 2025",
                "description": "",
                "favourites_count": 5,
                "followers_count": 3,
                "listed_count": 1,
                "media_count": 0,
                "profile_image_url": "https://pbs.twimg.com/profile_images/1906741063530016768/1Ka_4H8C_normal.png",
                "profile_banner_url": null,
                "statuses_count": 15,
                "verified": false,
                "is_blue_verified": false,
                "entities": {
                    "description": {
                        "urls": []
                    },
                    "url": null
                },
                "can_dm": false,
                "can_media_tag": true,
                "location": "",
                "pinned_tweet_ids": []
            },
            "id": "1910612683029962794",
            "text": "Technology has become an integral part of modern life, transforming how we communicate, work, and access information. With the rise of smartphones, artificial intelligence, and high-speed internet, daily tasks have become more efficient and convenient. However, this rapid",
            "reply_count": 1,
            "retweet_count": 1,
            "like_count": 0,
            "quote_count": 1,
            "bookmark_count": 0,
            "url": "https://x.com/ralatha_/status/1910612683029962794",
            "created_at": "Fri Apr 11 08:35:35 +0000 2025",
            "media": [],
            "is_quote_tweet": false,
            "is_retweet": false,
            "lang": "en",
            "conversation_id": "1910612683029962794",
            "in_reply_to_screen_name": null,
            "in_reply_to_status_id": null,
            "in_reply_to_user_id": null,
            "quoted_status_id": null,
            "quote": null,
            "display_text_range": [
                0,
                272
            ],
            "entities": {
                "hashtags": [],
                "media": [],
                "symbols": [],
                "timestamps": [],
                "urls": [],
                "user_mentions": []
            },
            "extended_entities": {
                "media": []
            }
        },
        "display_text_range": [
            0,
            3
        ],
        "entities": {
            "hashtags": [],
            "media": [],
            "symbols": [],
            "timestamps": [],
            "urls": [],
            "user_mentions": []
        },
        "extended_entities": {
            "media": []
        }
    }""")

    interaction = _tweet_to_interaction(quote, social_account=quote["user"], interaction_type=models.InteractionType.QUOTE)
    print(interaction)

if __name__ == "__main__":
    test_quote_to_interaction()
