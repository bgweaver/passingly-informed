import fetch from 'node-fetch';
import dotenv from 'dotenv';
import fs from 'fs';
import readline from 'readline';
import path from 'path';
import { getMetaDescription, getFullArticleContent } from './getMetaDescription.js';
import { getTeamsFromZip } from './zip_lookup.js';
import { createUser, listUsers, selectUser, getUserById, updateUserDigestDate } from './userManager.js';
import { generateDigestWithGroq, testGroqConnection } from './groqClient.js';

dotenv.config();

const NEWSDATA_API_KEY = process.env.NEWSDATA_API_KEY;
const GROQ_API_KEY = process.env.GROQ_API_KEY;

// Enhanced story importance scoring with season awareness
const IMPORTANCE_KEYWORDS = {
  high: ['playoff', 'championship', 'finals', 'trade', 'injury', 'suspended', 'fired', 'hired', 'record', 'milestone', 'controversy', 'scandal', 'breaking', 'draft', 'free agent', 'contract'],
  medium: ['win', 'loss', 'victory', 'defeat', 'score', 'game', 'match', 'season', 'signing', 'waiver', 'call-up', 'send down', 'lineup', 'roster'],
  low: ['practice', 'training', 'interview', 'comment', 'statement', 'rumor', 'report', 'update']
};

function calculateStoryImportance(article) {
  const text = `${article.title} ${article.description || ''}`.toLowerCase();
  let score = 0;
  
  // Base scoring
  IMPORTANCE_KEYWORDS.high.forEach(keyword => {
    if (text.includes(keyword)) score += 10;
  });
  
  IMPORTANCE_KEYWORDS.medium.forEach(keyword => {
    if (text.includes(keyword)) score += 5;
  });
  
  IMPORTANCE_KEYWORDS.low.forEach(keyword => {
    if (text.includes(keyword)) score += 1;
  });
  
  // Boost for recent articles
  if (article.pubDate) {
    const articleDate = new Date(article.pubDate);
    const now = new Date();
    const hoursOld = (now - articleDate) / (1000 * 60 * 60);
    
    if (hoursOld < 6) score += 5;      // Very recent
    else if (hoursOld < 24) score += 3; // Recent
    else if (hoursOld < 48) score += 1; // Somewhat recent
  }
  
  // Season-specific boosts
  const currentMonth = new Date().getMonth() + 1;
  const seasonalBoosts = {
    'nfl': [9, 10, 11, 12, 1],
    'nba': [10, 11, 12, 1, 2, 3, 4],
    'mlb': [3, 4, 5, 6, 7, 8, 9, 10],
    'nhl': [10, 11, 12, 1, 2, 3, 4],
    'mls': [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
  };
  
  Object.entries(seasonalBoosts).forEach(([sport, months]) => {
    if (months.includes(currentMonth) && text.includes(sport)) {
      score += 3; // In-season boost
    }
  });
  
  return score;
}

// Article deduplication with improved similarity detection
function deduplicateArticles(articles) {
  const seen = new Set();
  const duplicates = [];
  
  const unique = articles.filter(article => {
    const normalizedTitle = article.title.toLowerCase()
      .replace(/[^\w\s]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    
    const normalizedDesc = (article.description || '').toLowerCase()
      .replace(/[^\w\s]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .substring(0, 100);
    
    const identifier = `${normalizedTitle}::${normalizedDesc}`;
    
    // Check for very similar titles
    for (const seenId of seen) {
      const [seenTitle] = seenId.split('::');
      if (calculateSimilarity(normalizedTitle, seenTitle) > 0.8) {
        duplicates.push({
          duplicate: article.title,
          original: seenTitle,
          similarity: calculateSimilarity(normalizedTitle, seenTitle)
        });
        return false;
      }
    }
    
    if (seen.has(identifier)) {
      duplicates.push({
        duplicate: article.title,
        original: 'exact match',
        similarity: 1.0
      });
      return false;
    }
    
    seen.add(identifier);
    return true;
  });
  
  if (duplicates.length > 0) {
    console.log(`🔄 Removed ${duplicates.length} duplicate articles`);
  }
  
  return unique;
}

function calculateSimilarity(str1, str2) {
  const words1 = new Set(str1.split(' '));
  const words2 = new Set(str2.split(' '));
  
  const intersection = new Set([...words1].filter(word => words2.has(word)));
  const union = new Set([...words1, ...words2]);
  
  return intersection.size / union.size;
}

// Enhanced search strategy for user's teams
function buildSearchQueries(teams = []) {
  if (!teams || teams.length === 0) return ['sports'];

  const queries = [];
  
  // Individual team searches
  teams.forEach(team => {
    // Clean team name for better search
    const cleanTeam = team.replace(/^(New York|Los Angeles|San Francisco|San Antonio|Golden State|New England)/, '').trim();
    queries.push(`"${team}"`);
    if (cleanTeam !== team) {
      queries.push(`"${cleanTeam}"`);
    }
  });
  
  // Sport-specific searches for broader coverage
  const sportTerms = {
    'NFL': teams.filter(t => isNFLTeam(t)).length > 0 ? ['NFL football'] : [],
    'NBA': teams.filter(t => isNBATeam(t)).length > 0 ? ['NBA basketball'] : [],
    'MLB': teams.filter(t => isMLBTeam(t)).length > 0 ? ['MLB baseball'] : [],
    'NHL': teams.filter(t => isNHLTeam(t)).length > 0 ? ['NHL hockey'] : [],
    'MLS': teams.filter(t => isMLS(t)).length > 0 ? ['MLS soccer'] : []
  };
  
  Object.values(sportTerms).flat().forEach(term => queries.push(term));
  
  return queries.slice(0, 8); // Limit to avoid too many API calls
}

// Team sport detection helpers
function isNFLTeam(team) {
  const nflKeywords = ['patriots', 'eagles', 'cowboys', 'packers', 'steelers', 'ravens', 'chiefs', 'bills', 'titans', 'colts', 'texans', 'jaguars', 'broncos', 'raiders', 'chargers', 'seahawks', 'rams', 'cardinals', '49ers', 'bears', 'lions', 'vikings', 'falcons', 'panthers', 'saints', 'buccaneers', 'giants', 'jets', 'dolphins', 'browns', 'bengals', 'commanders'];
  return nflKeywords.some(keyword => team.toLowerCase().includes(keyword));
}

function isNBATeam(team) {
  const nbaKeywords = ['lakers', 'warriors', 'celtics', 'heat', 'bulls', 'knicks', 'nets', 'sixers', '76ers', 'cavaliers', 'pistons', 'pacers', 'bucks', 'hawks', 'hornets', 'magic', 'wizards', 'raptors', 'mavericks', 'rockets', 'spurs', 'grizzlies', 'pelicans', 'thunder', 'nuggets', 'jazz', 'blazers', 'kings', 'clippers', 'suns', 'timberwolves'];
  return nbaKeywords.some(keyword => team.toLowerCase().includes(keyword));
}

function isMLBTeam(team) {
  const mlbKeywords = ['yankees', 'red sox', 'dodgers', 'giants', 'cubs', 'cardinals', 'braves', 'phillies', 'mets', 'nationals', 'marlins', 'tigers', 'guardians', 'white sox', 'twins', 'royals', 'brewers', 'reds', 'pirates', 'astros', 'rangers', 'athletics', 'angels', 'mariners', 'rays', 'blue jays', 'orioles', 'diamondbacks', 'rockies', 'padres'];
  return mlbKeywords.some(keyword => team.toLowerCase().includes(keyword));
}

function isNHLTeam(team) {
  const nhlKeywords = ['bruins', 'rangers', 'penguins', 'capitals', 'flyers', 'devils', 'islanders', 'sabres', 'maple leafs', 'senators', 'canadiens', 'lightning', 'panthers', 'hurricanes', 'blue jackets', 'red wings', 'blackhawks', 'blues', 'predators', 'wild', 'avalanche', 'stars', 'flames', 'oilers', 'canucks', 'kings', 'ducks', 'sharks', 'golden knights', 'kraken', 'coyotes'];
  return nhlKeywords.some(keyword => team.toLowerCase().includes(keyword));
}

function isMLS(team) {
  const mlsKeywords = ['galaxy', 'lafc', 'sounders', 'timbers', 'fire', 'crew', 'revolution', 'united', 'city', 'fc'];
  return mlsKeywords.some(keyword => team.toLowerCase().includes(keyword));
}

// Multi-query news fetching with better error handling
async function fetchMultipleQueries(queries) {
  const allArticles = [];
  
  for (const query of queries) {
    console.log(`🔍 Searching for: ${query}`);
    
    const baseUrl = 'https://newsdata.io/api/1/news';
    const params = new URLSearchParams({
      apikey: NEWSDATA_API_KEY,
      q: query,
      language: 'en',
      category: 'sports',
      size: 10 // Limit per query
    });

    const url = `${baseUrl}?${params.toString()}`;
    
    try {
      const res = await fetch(url);
      
      if (!res.ok) {
        console.error(`❌ HTTP Error for query "${query}": ${res.status}`);
        continue;
      }
      
      const data = await res.json();
      
      if (data.status === 'error') {
        console.error(`❌ API Error for query "${query}":`, data.results?.message || 'Unknown error');
        continue;
      }
      
      if (data.results && Array.isArray(data.results)) {
        console.log(`📰 Found ${data.results.length} articles for "${query}"`);
        allArticles.push(...data.results);
      }
      
      // Rate limiting
      await new Promise(resolve => setTimeout(resolve, 1000));
      
    } catch (error) {
      console.error(`❌ Error fetching query "${query}":`, error.message);
    }
  }
  
  return allArticles;
}

// Enhanced article processing with source tracking
function processArticles(articles, city, isWeekly) {
  console.log(`📊 Processing ${articles.length} total articles...`);
  
  // Enhanced filtering
  let cleanResults = articles.filter(item =>
    item.title &&
    item.description &&
    item.description.length > 50 &&
    !item.description.includes("ONLY AVAILABLE IN PAID PLANS") &&
    !item.title.toLowerCase().match(/cricket|betting|fantasy|gambling|stock|earnings|financial/) &&
    !item.source_id?.toLowerCase().includes("baseballnewssource") &&
    item.link && // Ensure valid link
    !item.link.includes('youtube.com') // Exclude video content
  );
  
  console.log(`📝 After basic filtering: ${cleanResults.length} articles`);
  
  // Deduplication
  cleanResults = deduplicateArticles(cleanResults);
  console.log(`🔄 After deduplication: ${cleanResults.length} articles`);
  
  // Date filtering
  const now = new Date();
  const cutoff = new Date();
  cutoff.setDate(now.getDate() - (isWeekly ? 7 : 3)); // 3 days for daily, 7 for weekly
  
  cleanResults = cleanResults.filter(article => {
    if (!article.pubDate) return true;
    return new Date(article.pubDate) > cutoff;
  });
  
  console.log(`📅 After date filtering: ${cleanResults.length} articles`);
  
  // Calculate importance scores
  cleanResults.forEach(article => {
    article.importanceScore = calculateStoryImportance(article);
  });
  
  // Enhanced sorting with source quality
  const trustedDomains = [
    'espn.com', 'nfl.com', 'nba.com', 'mlb.com', 'nhl.com', 'mls.com',
    'si.com', 'yahoo.com', 'cbssports.com', 'foxsports.com', 
    'bleacherreport.com', 'theathletic.com', 'sbnation.com',
    'ap.org', 'reuters.com'
  ];
  
  cleanResults.sort((a, b) => {
    // Importance score first
    if (b.importanceScore !== a.importanceScore) {
      return b.importanceScore - a.importanceScore;
    }
    
    // Trusted source boost
    const aIsTrusted = trustedDomains.some(domain => a.link?.includes(domain));
    const bIsTrusted = trustedDomains.some(domain => b.link?.includes(domain));
    
    if (aIsTrusted && !bIsTrusted) return -1;
    if (!aIsTrusted && bIsTrusted) return 1;
    
    // Publication date
    if (a.pubDate && b.pubDate) {
      return new Date(b.pubDate) - new Date(a.pubDate);
    }
    
    return 0;
  });
  
  return cleanResults;
}

// Enhanced file saving with metadata
async function saveDigestToFile(content, user, metadata, isWeekly) {
  try {
    const now = new Date();
    const dateStr = now.toISOString().split('T')[0];
    const timeframe = isWeekly ? 'weekly' : 'daily';
    const filename = `${user.name.toLowerCase().replace(/\s+/g, '-')}-${user.city.toLowerCase().replace(/\s+/g, '-')}-${dateStr}-${timeframe}.txt`;
    
    const outputDir = './outputs';
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    
    const filepath = path.join(outputDir, filename);
    const timestamp = now.toLocaleString();
    
    const fileContent = `Generated: ${timestamp}
User: ${user.name} (${user.city}, ${user.state})
Teams: ${user.selectedTeams.join(', ')}
Articles processed: ${metadata.totalArticles}
Sources analyzed: ${metadata.sources}
Model used: ${metadata.model}
Season analysis: ${JSON.stringify(metadata.seasonAnalysis, null, 2)}

${content}`;
    
    fs.writeFileSync(filepath, fileContent, 'utf8');
    console.log(`💾 Digest saved to: ${filepath}`);
    
  } catch (error) {
    console.error('❌ Error saving file:', error);
  }
}

// Main digest generation function for users
export async function generateDigestForUser(user, isWeekly = false) {
  console.log(`🚀 Generating ${isWeekly ? 'weekly' : 'daily'} digest for ${user.name}`);
  console.log(`📍 Location: ${user.city}, ${user.state}`);
  console.log(`🏆 Teams: ${user.selectedTeams.join(', ')}`);
  
  try {
    // Build search queries based on user's teams
    const queries = buildSearchQueries(user.selectedTeams);
    console.log(`🔍 Will search with ${queries.length} queries`);
    
    // Fetch articles
    const allArticles = await fetchMultipleQueries(queries);
    console.log(`📊 Total articles collected: ${allArticles.length}`);
    
    if (allArticles.length === 0) {
      console.log(`❌ No articles found for ${user.name}'s teams.`);
      return null;
    }
    
    // Process articles
    const cleanResults = processArticles(allArticles, user.city, isWeekly);
    
    if (cleanResults.length === 0) {
      console.log(`❌ No usable articles after processing.`);
      return null;
    }
    
    console.log(`📰 Processing ${cleanResults.length} final articles...`);
    
    // Build digest text with enhanced content
    let digestText = `Sports digest for ${user.name} in ${user.city}, ${user.state}\n`;
    digestText += `Teams following: ${user.selectedTeams.join(', ')}\n`;
    digestText += `Timeframe: ${isWeekly ? 'Past 7 days' : 'Past 3 days'}\n`;
    digestText += `Articles processed: ${allArticles.length} → ${cleanResults.length} final\n\n`;
    
    const sources = [];
    const maxArticles = isWeekly ? 10 : 8;
    
    for (let i = 0; i < Math.min(cleanResults.length, maxArticles); i++) {
      const item = cleanResults[i];
      
      console.log(`📖 Processing article ${i + 1}: ${item.title}`);
      
      // Try to get enhanced content
      const enhancedContent = await getFullArticleContent(item.link);
      const meta = enhancedContent || await getMetaDescription(item.link) || item.description;
      
      digestText += `${i + 1}. ${item.title}\n`;
      digestText += `Source: ${item.source_id || 'Unknown'} (${new URL(item.link).hostname})\n`;
      digestText += `Published: ${item.pubDate || 'Unknown date'}\n`;
      digestText += `Importance: ${item.importanceScore}/10\n`;
      digestText += `Content: ${meta}\n`;
      digestText += `URL: ${item.link}\n\n`;
      
      sources.push(item.link);
      
      // Small delay to be respectful
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    // Generate digest with Groq
    const digestResult = await generateDigestWithGroq(
      digestText, 
      sources, 
      user.city, 
      user.selectedTeams, 
      user.name, 
      isWeekly, 
      GROQ_API_KEY
    );
    
    if (digestResult) {
      // Save digest with metadata
      const metadata = {
        totalArticles: allArticles.length,
        finalArticles: cleanResults.length,
        sources: sources.length,
        model: digestResult.model,
        seasonAnalysis: digestResult.seasonAnalysis
      };
      
      await saveDigestToFile(digestResult.content, user, metadata, isWeekly);
      
      // Update user's last digest date
      updateUserDigestDate(user.id);
      
      return digestResult.content;
    }
    
    return null;
    
  } catch (error) {
    console.error('❌ Error generating digest:', error);
    return null;
  }
}

// Interactive dashboard
async function runDashboard() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true
  });
  
  // Disable raw mode to prevent double character input
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }
  
  const question = (prompt) => new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      // Clean the answer to handle any terminal artifacts
      resolve(answer.trim());
    });
  });
  
  try {
    console.log('\n🏈 Passingly Informed Sports Digest Generator 🏀');
    console.log('='.repeat(60));
    console.log('📱 Console Version - User Management System');
    console.log('='.repeat(60));
    
    // Test API connections
    if (GROQ_API_KEY) {
      console.log('\n🧪 Testing API connections...');
      await testGroqConnection(GROQ_API_KEY);
    } else {
      console.log('⚠️  Warning: GROQ_API_KEY not found in .env file');
    }
    
    while (true) {
      console.log('\n📋 Main Menu:');
      console.log('1. Create new user');
      console.log('2. List users');
      console.log('3. Generate digest for user');
      console.log('4. Test ZIP lookup');
      console.log('5. Exit');
      
      const choice = await question('\nEnter your choice (1-5): ');
      
      switch (choice) {
        case '1':
          console.log('\n🆕 Creating new user...');
          rl.close(); // Close current interface
          await createUser();
          // Recreate interface for next iteration
          const newRl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
            terminal: true
          });
          Object.assign(rl, newRl);
          break;
          
        case '2':
          listUsers();
          break;
          
        case '3':
          console.log('\n👤 Select user for digest generation...');
          rl.close(); // Close current interface
          const user = await selectUser();
          
          if (user) {
            // Create new interface for digest options
            const digestRl = readline.createInterface({
              input: process.stdin,
              output: process.stdout,
              terminal: true
            });
            
            const digestQuestion = (prompt) => new Promise((resolve) => {
              digestRl.question(prompt, (answer) => resolve(answer.trim()));
            });
            
            try {
              console.log('\n📅 Choose digest type:');
              console.log('1. Daily digest');
              console.log('2. Weekly digest');
              
              const digestChoice = await digestQuestion('Enter choice (1 or 2): ');
              const isWeekly = digestChoice === '2';
              
              console.log(`\n🚀 Generating ${isWeekly ? 'weekly' : 'daily'} digest for ${user.name}...`);
              console.log('This may take a few minutes...\n');
              
              const result = await generateDigestForUser(user, isWeekly);
              
              if (result) {
                console.log('\n✅ Digest generated successfully!');
                console.log('📁 Check the ./outputs directory for your saved digest file.');
              } else {
                console.log('\n❌ Failed to generate digest. Please check the logs above.');
              }
              
            } finally {
              digestRl.close();
            }
          }
          
          // Recreate main interface
          const mainRl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
            terminal: true
          });
          Object.assign(rl, mainRl);
          break;
          
        case '4':
          const testZip = await question('Enter ZIP code to test: ');
          console.log('\n🔍 Testing ZIP lookup...');
          const result = await getTeamsFromZip(testZip);
          if (result) {
            console.log(`📍 Location: ${result.city}, ${result.state}`);
            console.log(`🏆 Teams: ${result.teams.join(', ')}`);
            console.log(`📊 Source: ${result.source} (${result.confidence} confidence)`);
          } else {
            console.log('❌ No results found for that ZIP code');
          }
          break;
          
        case '5':
          console.log('\n👋 Thanks for using Passingly Informed!');
          console.log('🎯 Remember: You\'re now passingly informed about sports!');
          rl.close();
          return;
          
        case '':
          // Handle empty input gracefully
          console.log('ℹ️  Please enter a number from 1-5');
          break;
          
        default:
          console.log(`❌ Invalid choice: "${choice}". Please enter 1, 2, 3, 4, or 5.`);
      }
    }
    
  } catch (error) {
    console.error('❌ Error in dashboard:', error);
    console.log('\n🔄 Restarting dashboard...');
    // Try to restart the dashboard
    setTimeout(() => runDashboard(), 1000);
  } finally {
    rl.close();
  }
}

// Legacy function for backward compatibility
export async function fetchNewsByZip(zipCode, recipientName = 'there', isWeekly = false) {
  console.log('⚠️  Note: fetchNewsByZip is deprecated. Please use the user management system.');
  
  const zipResult = await getTeamsFromZip(zipCode);
  if (!zipResult) return null;
  
  // Create temporary user object
  const tempUser = {
    name: recipientName,
    zipCode,
    city: zipResult.city,
    state: zipResult.state,
    selectedTeams: zipResult.teams.slice(0, 5), // Limit to 5 teams
    id: 'temp'
  };
  
  return await generateDigestForUser(tempUser, isWeekly);
}

// Main execution
async function main() {
  const args = process.argv.slice(2);
  
  if (args.length === 0) {
    await runDashboard();
  } else if (args[0] === 'legacy' && args.length >= 2) {
    // Legacy mode for backward compatibility
    const zipCode = args[1];
    const name = args[2] || 'there';
    const isWeekly = args[3] === 'weekly';
    
    console.log(`🚀 Legacy mode: Fetching sports news for ZIP code: ${zipCode}`);
    await fetchNewsByZip(zipCode, name, isWeekly);
  } else {
    console.log('Usage:');
    console.log('  node index.js                    # Interactive dashboard');
    console.log('  node index.js legacy <zip> [name] [weekly]  # Legacy mode');
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}