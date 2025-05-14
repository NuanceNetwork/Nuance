---
hide:
  - navigation
#   - toc
---

# Nuance

## Introduction

Nuance is a revolutionary subnet project aimed at transforming the media landscape by incentivizing users on X to promote factual and nuanced opinions.

Our vision is to create a decentralized swarm that assist humans in understanding contemporary issues in a fair and transparent manner.

## Incentive Mechanism

In this subnet, miners are rewarded for contributing factual and nuanced posts and comments. The reward system is designed to encourage high-quality content by basing rewards on the engagement received from verified accounts. Here's how it works:

- **Objective**: To challenge media giants by fostering a community that values factual and nuanced discourse.
- **Mechanism**: Miners are incentivized to create content that is both factual and nuanced. Their rewards are determined by the level of engagement their content receives from verified users.
- **Engagement**: The focus is on interactions such as replies, which are currently easier to track on X, but the system is designed to be adaptable to other social platforms in the future.

The validator implements this incentive mechanism through several key steps:

1. **Account Verification**: Miners commit their X account username and verification post ID on-chain. Validators verify miners by checking that the verification post quotes the Nuance announcement post and contains the miner's hotkey.

2. **Content Discovery**: Validators query on-chain commits to retrieve miners' X accounts. They then discover new posts made by miners, filtering them through Large Language Models (LLM) to ensure the content is nuanced and relevant to specific subjects, such as bittensor.

3. **Interaction Analysis**: Validators identify interactions with miners' posts, filtering them for positivity and ensuring they originate from a list of verified users.

4. **Scoring**: Interactions are scored based on multiple factors:
   - **Interaction Type**: Replies is the only supported interaction type at the moment
   - **Recency**: Only interactions within the last 14 days are considered, with newer interactions weighted higher
   - **Account Influence**: Higher scores for interactions from accounts with more followers
   - **Content Categories**: Scores are weighted by topic categories, allowing emphasis on specific subjects

5. **Score Aggregation**: Final scores are calculated by:
   - Normalizing scores within each category
   - Applying category weights to prioritize certain topics
   - Setting weights on the Bittensor chain to determine miner rewards

This approach ensures that quality content receives appropriate recognition while maintaining focus on the most relevant topics for the community.

## Validator Setup

For detailed instructions on setting up validators, please refer to the [full documentation](./validators.md).

## Miner Setup

For detailed instructions on setting up miners, please refer to the [full documentation](./miners.md).