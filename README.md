Passingly Informed Sports Digest
================================

A sports digest generator for people who don't care about sports but still want to sound like they do in casual conversations.

Features
--------

-   **ZIP Code-Based Team Detection**: Automatically finds your local sports teams based on your ZIP code
-   **Enhanced Article Parsing**: Extracts more detailed content from news articles for better context
-   **Story Prioritization**: Ranks articles by importance using keyword analysis and recency
-   **Daily/Weekly Options**: Choose between daily (2-day) or weekly (7-day) digests
-   **Interactive Dashboard**: Easy-to-use command-line interface
-   **File Output**: Saves digests to dated files in the `outputs/` directory
-   **Non-Sports Fan Friendly**: Explains sports terminology and provides context

Setup
-----

1.  **Install Dependencies**:

    bash

    ```
    npm install
    ```

2.  **Set Up Environment Variables**: Create a `.env` file in the root directory with:

    ```
    NEWSDATA_API_KEY=your_newsdata_api_key_here
    VENICE_API_KEY=your_venice_api_key_here
    ```

3.  **Get API Keys**:
    -   **NewsData API**: Sign up at [newsdata.io](https://newsdata.io) for news articles
    -   **Venice API**: Sign up at [venice.ai](https://venice.ai) for AI text generation

Usage
-----

### Interactive Dashboard (Recommended)

bash

```
npm start
```

or

bash

```
node index.js
```

This will prompt you for:

-   Your name
-   ZIP code
-   Daily or weekly digest preference

### Command Line Usage

bash

```
# Basic usage with ZIP code
node index.js 46201

# With custom name
node index.js 46201 "John"

# Weekly digest
node index.js 46201 "John" weekly
```

### Available Scripts

bash

```
npm run start          # Interactive dashboard
npm run daily          # Quick daily digest (uses default ZIP)
npm run weekly         # Quick weekly digest (uses default ZIP)
npm run test-zip       # Test ZIP code lookup system
```

How It Works
------------

1.  **Location Detection**: Uses your ZIP code to determine local sports teams
2.  **News Fetching**: Searches for recent sports news about your teams
3.  **Content Analysis**: Extracts and analyzes article content for importance
4.  **Story Prioritization**: Ranks stories by relevance and recency
5.  **Digest Generation**: Creates a casual, explanatory digest using AI
6.  **File Output**: Saves the digest to a dated file in `outputs/`

Output Format
-------------

The digest includes:

-   **What Happened**: 4-6 detailed bullet points with context for non-sports fans
-   **Say This to Sound Smart**: A conversation-ready one-liner
-   **Why It Matters**: Broader implications and context
-   **Quick Context**: Basic info about your local teams

File Structure
--------------

```
project/
├── index.js              # Main application with CLI dashboard
├── zip_lookup.js         # ZIP code to sports teams mapping
├── getMetaDescription.js # Enhanced article content extraction
├── package.json          # Dependencies and scripts
├── .env                  # API keys (create this)
├── outputs/              # Generated digest files (auto-created)
└── README.md            # This file
```

Output Files
------------

Files are saved as: `[city].[date].[daily|weekly].txt`

Examples:

-   `indianapolis.2024-01-15.daily.txt`
-   `chicago.2024-01-15.weekly.txt`

Supported Markets
-----------------

The system recognizes 50+ major sports markets and includes fallbacks for:

-   Metro areas (NYC, LA, Chicago, etc.)
-   State-level team assignments
-   College sports markets
-   Geographic proximity matches

Customization
-------------

### Adding New Teams/Markets

Edit the `SPORTS_MARKETS` object in `zip_lookup.js`:

javascript

```
"YourCity": ["Team1", "Team2", "Team3"]
```

### Adjusting Story Importance

Modify the `IMPORTANCE_KEYWORDS` object in `index.js`:

javascript

```
const IMPORTANCE_KEYWORDS = {
  high: ['your', 'keywords', 'here'],
  medium: ['medium', 'priority', 'words'],
  low: ['low', 'priority', 'terms']
};
```

### Changing Digest Tone

Update the prompt in the `sendToVenice` function in `index.js`.

Troubleshooting
---------------

### Common Issues

1.  **API Key Errors**: Ensure your `.env` file has valid API keys
2.  **ZIP Code Not Found**: The system falls back to state-level teams
3.  **No Articles Found**: Try a different timeframe or check your team mappings
4.  **Venice API Fails**: The system tries multiple AI models automatically

### Debug Mode

Add console.log statements or use the test functions:

bash

```
npm run test-zip  # Test ZIP code lookup
```

Requirements
------------

-   Node.js 18+
-   NewsData API key (free tier available)
-   Venice AI API key
-   Internet connection for API calls

Contributing
------------

1.  Fork the repository
2.  Create a feature branch
3.  Make your changes
4.  Test with various ZIP codes
5.  Submit a pull request

License
-------

MIT License - feel free to modify and use as needed.

* * * * *

*"Go forth and nod knowingly" - Statsworth*