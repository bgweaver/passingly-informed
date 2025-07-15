// groqClient.js - Groq API integration with season-aware digest generation
import fetch from 'node-fetch';

// Sport seasons configuration
const SPORT_SEASONS = {
  NFL: {
    active: [9, 10, 11, 12, 1], // Sep-Jan
    offseason: [2, 3, 4, 5, 6, 7, 8],
    description: "American Football"
  },
  NBA: {
    active: [10, 11, 12, 1, 2, 3, 4], // Oct-Apr
    offseason: [5, 6, 7, 8, 9],
    description: "Basketball"
  },
  MLB: {
    active: [3, 4, 5, 6, 7, 8, 9, 10], // Mar-Oct
    offseason: [11, 12, 1, 2],
    description: "Baseball"
  },
  NHL: {
    active: [10, 11, 12, 1, 2, 3, 4], // Oct-Apr
    offseason: [5, 6, 7, 8, 9],
    description: "Hockey"
  },
  MLS: {
    active: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11], // Feb-Nov
    offseason: [12, 1],
    description: "Soccer"
  }
};

// Determine sport from team name
function getTeamSport(teamName) {
  const sportKeywords = {
    NFL: ['patriots', 'eagles', 'cowboys', 'packers', 'steelers', 'ravens', 'chiefs', 'bills', 'titans', 'colts', 'texans', 'jaguars', 'broncos', 'raiders', 'chargers', 'seahawks', 'rams', 'cardinals', '49ers', 'bears', 'lions', 'vikings', 'falcons', 'panthers', 'saints', 'buccaneers', 'giants', 'jets', 'dolphins', 'browns', 'bengals', 'commanders'],
    NBA: ['lakers', 'warriors', 'celtics', 'heat', 'bulls', 'knicks', 'nets', 'sixers', '76ers', 'cavaliers', 'pistons', 'pacers', 'bucks', 'hawks', 'hornets', 'magic', 'wizards', 'raptors', 'mavericks', 'rockets', 'spurs', 'grizzlies', 'pelicans', 'thunder', 'nuggets', 'jazz', 'blazers', 'kings', 'clippers', 'suns', 'timberwolves'],
    MLB: ['yankees', 'red sox', 'dodgers', 'giants', 'cubs', 'cardinals', 'braves', 'phillies', 'mets', 'nationals', 'marlins', 'tigers', 'guardians', 'white sox', 'twins', 'royals', 'indians', 'brewers', 'reds', 'pirates', 'astros', 'rangers', 'athletics', 'angels', 'mariners', 'rays', 'blue jays', 'orioles', 'diamondbacks', 'rockies', 'padres'],
    NHL: ['bruins', 'rangers', 'penguins', 'capitals', 'flyers', 'devils', 'islanders', 'sabres', 'maple leafs', 'senators', 'canadiens', 'lightning', 'panthers', 'hurricanes', 'blue jackets', 'red wings', 'blackhawks', 'blues', 'predators', 'wild', 'avalanche', 'stars', 'flames', 'oilers', 'canucks', 'kings', 'ducks', 'sharks', 'golden knights', 'kraken', 'coyotes'],
    MLS: ['galaxy', 'lafc', 'sounders', 'timbers', 'fire', 'crew', 'revolution', 'united', 'city', 'fc']
  };
  
  const teamLower = teamName.toLowerCase();
  
  for (const [sport, keywords] of Object.entries(sportKeywords)) {
    if (keywords.some(keyword => teamLower.includes(keyword))) {
      return sport;
    }
  }
  
  return 'Unknown';
}

// Analyze teams by season status
function analyzeTeamSeasons(teams) {
  const currentMonth = new Date().getMonth() + 1;
  const analysis = {
    inSeason: [],
    offSeason: [],
    unknown: []
  };
  
  teams.forEach(team => {
    const sport = getTeamSport(team);
    
    if (sport === 'Unknown') {
      analysis.unknown.push({ team, sport });
      return;
    }
    
    const seasonInfo = SPORT_SEASONS[sport];
    if (seasonInfo.active.includes(currentMonth)) {
      analysis.inSeason.push({ team, sport, description: seasonInfo.description });
    } else {
      analysis.offSeason.push({ team, sport, description: seasonInfo.description });
    }
  });
  
  return analysis;
}

// Generate season-aware digest with Groq
export async function generateDigestWithGroq(digestText, sources, city, teams, recipientName, isWeekly, groqApiKey) {
  try {
    const seasonAnalysis = analyzeTeamSeasons(teams);
    const timeframe = isWeekly ? 'weekly' : 'daily';
    
    // Build context about team seasons
    let seasonContext = '';
    if (seasonAnalysis.inSeason.length > 0) {
      const inSeasonSports = [...new Set(seasonAnalysis.inSeason.map(t => t.sport))];
      seasonContext += `Currently in season: ${inSeasonSports.join(', ')}. `;
    }
    if (seasonAnalysis.offSeason.length > 0) {
      const offSeasonSports = [...new Set(seasonAnalysis.offSeason.map(t => t.sport))];
      seasonContext += `Currently off-season: ${offSeasonSports.join(', ')}. `;
    }
    
    const models = ['mixtral-8x7b-32768', 'llama3-70b-8192', 'llama3-8b-8192'];
    
    for (const model of models) {
      console.log(`🤖 Trying Groq model: ${model}`);
      
      const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${groqApiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: model,
          messages: [
            {
              role: 'system',
              content: `You are writing a ${timeframe} sports digest called "Passingly Informed" for people who don't care about sports but still want to sound like they do in casual conversations. Your audience consists of complete sports novices who need context and explanations.

Key instructions:
- Write for people who know NOTHING about sports
- Explain all jargon and context
- Focus on human drama, money, local pride, and office water cooler topics
- Be conversational and slightly humorous
- Prioritize in-season sports but include interesting off-season news too
- Make it useful for casual conversations

Current season context: ${seasonContext}

Format requirements:
- Use exactly this email subject line
- Include 4-6 detailed bullet points with full context
- Provide a natural conversation starter
- Explain why non-sports fans should care
- Give quick context about the teams for newcomers`
            },
            {
              role: 'user',
              content: `Write the digest in this exact format:

---
Subject: You're Passingly Informed: ${city} Sports Digest (${timeframe.charAt(0).toUpperCase() + timeframe.slice(1)})

Hey ${recipientName},

Here's your ${timeframe} digest of sports things you didn't ask for but might need to fake knowing:

🧠 What Happened:
• (Write 4-6 detailed bullet points explaining what happened AND why it matters. Each should be 2-3 sentences that explain the context for non-sports fans. Include team names, what sport they play, and why this news is significant. Make it conversational and explain any jargon.)

💬 Say This to Sound Smart:
"Write a one-liner someone might say in conversation, referencing one of the main events. Make it sound natural and include enough context that a non-sports person could use it."

👀 Why It Matters:
(Write 2-3 sentences explaining the broader implications. Connect it to things non-sports fans understand: office culture, local pride, drama, money, or seasonal significance.)

🎯 Quick Context:
(Write 1-2 sentences explaining what ${teams.join(' and ')} are, what sports they play, and their general status/reputation for newcomers. Mention which are currently in season vs off-season.)

Sources: ${sources.length} articles analyzed

That's all. Go forth and nod knowingly,  
—Statsworth

---

Important guidelines:
- If it's football season, prioritize NFL news but include other sports
- If it's basketball/hockey season, balance coverage appropriately  
- Even off-season news can be interesting (trades, scandals, prep for next season)
- Explain why timing matters (playoffs, trade deadlines, etc.)
- Connect to local culture and pride
- Make bullet points substantial - 2-3 sentences each minimum
- Focus on the most important/interesting stories first

Base the summary ONLY on these articles:

${digestText}

If there's limited news, acknowledge it but still provide context about what's normal for this time of year and what to expect next.`,
            }
          ],
          temperature: 0.7,
          max_tokens: 1000,
          top_p: 1,
          stream: false
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        const content = data.choices?.[0]?.message?.content;
        
        if (content) {
          console.log('\n' + '='.repeat(60));
          console.log('📧 GENERATED DIGEST (via Groq):');
          console.log('='.repeat(60));
          console.log(content);
          console.log('='.repeat(60));
          
          return {
            content,
            model: model,
            seasonAnalysis,
            sources: sources.length
          };
        }
      } else {
        const errorData = await response.text();
        console.warn(`⚠️ Model ${model} failed: ${response.status} - ${errorData}`);
      }
    }
    
    console.error('❌ All Groq models failed. Check your API key and quota.');
    return null;
    
  } catch (error) {
    console.error('❌ Error calling Groq API:', error);
    return null;
  }
}

// Test Groq connection
export async function testGroqConnection(apiKey) {
  try {
    console.log('🧪 Testing Groq API connection...');
    
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'llama3-8b-8192',
        messages: [
          {
            role: 'user',
            content: 'Hello! Just testing the connection. Please respond with "Connection successful!"'
          }
        ],
        max_tokens: 50
      })
    });
    
    if (response.ok) {
      const data = await response.json();
      console.log('✅ Groq API connection successful!');
      console.log(`📝 Response: ${data.choices[0].message.content}`);
      return true;
    } else {
      const error = await response.text();
      console.error('❌ Groq API connection failed:', error);
      return false;
    }
    
  } catch (error) {
    console.error('❌ Error testing Groq connection:', error);
    return false;
  }
}