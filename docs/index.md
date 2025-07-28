---
hide:
  - navigation
#   - toc
---

# Nuance

## Introduction

Nuance is a revolutionary subnet project aimed at transforming the media landscape by incentivizing users on X to promote factual and nuanced opinions.

Our vision is to create a decentralized swarm that assists humans in understanding contemporary issues in a fair and transparent manner.

## Quick Links

- **🌐 [Main Website](https://www.nuance.info/)** - General information, subnet status, and performance tracking
- **📚 [Documentation](https://www.docs.nuance.info/)** - Complete guides and API interface for content submission
- **🔗 [API Explorer](http://api.nuance.info/scalar)** - Browse subnet data, check scores, and explore posts/interactions
- **🐦 [Follow us on X](https://x.com/NuanceSubnet)** - Latest updates and official announcements

## How It Works

### For Miners

1. **Account Verification**: Connect your X account by either:
   - Including specific hashtags in your posts, or
   - Creating a verification post that replies to or quotes any post from the [Nuance subnet's X account](https://x.com/NuanceSubnet), containing your miner hotkey

2. **Content Submission**: Submit your factual and nuanced posts through:
   - **[Documentation Portal](https://www.docs.nuance.info/)** (recommended for easy submission)
   - **Validator Axons** (check metagraph for validator endpoints)

3. **Earn Rewards**: Get rewarded based on:
   - Quality interactions (replies) from verified community members
   - Your own posts (if you own a verified account)
   - Content relevance to current topics of interest

### For Validators

Validators process content through this hybrid workflow:

1. **Content Discovery**: Currently accepts content through:
   - **Direct submission APIs** (recommended method)
   - **Content scraping** from verified miners' X accounts (being phased out)
2. **Quality Filtering**: Use LLMs to verify content is nuanced and relevant to specific topics
3. **Interaction Analysis**: Score positive interactions from verified community members
4. **Dynamic Scoring**: Calculate rewards using a multi-factor system:
   - **Engagement Quality**: Different interaction types have varying weights
   - **Account Influence**: Higher scores for interactions from weighted community members
   - **7-Day Window**: Only interactions from the last 7 days are considered for scoring
   - **Anti-Spam Protection**: Capped scoring per user to prevent gaming
   - **Topic Categories**: Content scored by relevance to current focus areas

5. **Weight Setting**: Aggregate scores across categories and set network weights

### Scoring Formula

The scoring system balances engagement quality and prevents spam:

```
Base Score = f(engagement_count) where:
- 1 engagement = 1.0 points
- 2 engagements = 1.7 points  
- 3+ engagements = 2.0 points
(then divided by total engagements per account)

Final Score = Base Score × Interaction Weight × User Influence × Topic Weight
```

## Getting Started

- **Miners**: Visit our [documentation](https://www.docs.nuance.info/) for setup guides and submission tools
- **Validators**: See the sections below for detailed setup instructions
- **Community**: Explore the [API](http://api.nuance.info/scalar) to track subnet performance and your contributions

## Validator Setup

For detailed instructions on setting up validators, please refer to the [full documentation](docs/validator.md).

## Miner Setup

For detailed instructions on setting up miners, please refer to the [full documentation](docs/miner.md).

---

*Building a more nuanced discourse, one interaction at a time.*