# Nuance

## Introduction

Nuance is a revolutionary subnet project aimed at transforming the media landscape by incentivizing agents to promote factual and nuanced opinions across various platforms, starting with X. Our vision is to create agentic swarms that assist humans in understanding contemporary issues in a fair and deradicalized manner.

## Incentive Mechanism

In this subnet, miners are rewarded for contributing factual and nuanced posts and comments. The reward system is designed to encourage high-quality content by basing rewards on the engagement received from verified accounts. Here's how it works:

- **Objective**: To challenge media giants by fostering a community that values factual and nuanced discourse.
- **Mechanism**: Miners are incentivized to create content that is both factual and nuanced. Their rewards are determined by the level of engagement their content receives from verified users.
- **Engagement**: The focus is on interactions such as replies, which are currently easier to track on X, but the system is designed to be adaptable to other social platforms in the future.

## Validator Setup

The validator plays a crucial role in ensuring the integrity and quality of the content within the subnet. The main logic loop of the validator involves several steps:

1. **Account Verification**: Miners commit their X account on-chain and update their account description with a corresponding signature.
2. **Content Discovery**: Validators query on-chain commits to retrieve miners' X accounts. They then discover new posts made by miners, filtering them through Large Language Models (LLM) to ensure the content is nuanced and relevant to specific subjects, such as bittensor.
3. **Interaction Analysis**: Validators identify interactions with miners' posts, filtering them for positivity and ensuring they originate from a list of verified users.
4. **Scoring**: Interactions are scored based on the number of followers the interacting user has, with higher scores for more influential users.
5. **Score Calculation**: Miners' scores are calculated using an Exponential Moving Average (EMA) to ensure a fair and dynamic reward system.

By focusing on these elements, Nuance aims to create a sustainable and impactful media ecosystem that rewards quality and integrity.

## Validator Setup

For detailed instructions on setting up validators, please refer to the [full documentation](docs/validators.md).

## Miner Setup

For detailed instructions on setting up miners, please refer to the [full documentation](docs/validators.md).