// newsPool.js - Daily news collection and weekly digest automation
import fs from 'fs';
import path from 'path';
import { fetchMultipleQueries, buildSearchQueries, processArticles } from './enhanced_index.js';
import { getFullArticleContent, getMetaDescription } from './getMetaDescription.js';
import { generateDigestWithGroq } from './groqClient.js';
import { getActiveWeeklyUsers, updateUserLastDigest, loadAdminConfig } from './adminSystem.js';

const NEWS_POOL_DIR = './data/news_pool';
const DIGEST_ARCHIVE_DIR = './outputs/weekly_archives';

// Ensure directories exist
function initializeDirectories() {
  [NEWS_POOL_DIR, DIGEST_ARCHIVE_DIR, './data', './outputs'].forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  });
}

// Get date string for file naming
function getDateString(date = new Date()) {
  return date.toISOString().split('T')[0]; // YYYY-MM-DD
}

// Get week identifier (Sunday to Saturday)
function getWeekIdentifier(date = new Date()) {
  const d = new Date(date);
  const day = d.getDay(); // 0 = Sunday
  const diff = d.getDate() - day; // Get Sunday of this week
  const sunday = new Date(d.setDate(diff));
  return getDateString(sunday);
}

// Save daily news collection
function saveDailyNews(date, teamNews) {
  const dateStr = getDateString(date);
  const filePath = path.join(NEWS_POOL_DIR, `${dateStr}.json`);
  
  const newsData = {
    date: dateStr,
    collectedAt: new Date().toISOString(),
    totalArticles: Object.values(teamNews).flat().length,
    teamNews
  };
  
  try {
    fs.writeFileSync(filePath, JSON.stringify(newsData, null, 2));
    console.log(`💾 Saved ${newsData.totalArticles} articles for ${dateStr}`);
    return true;
  } catch (error) {
    console.error(`❌ Error saving daily news for ${dateStr}:`, error);
    return false;
  }
}

// Load daily news from file
function loadDailyNews(date) {
  const dateStr = getDateString(date);
  const filePath = path.join(NEWS_POOL_DIR, `${dateStr}.json`);
  
  try {
    if (fs.existsSync(filePath)) {
      const data = fs.readFileSync(filePath, 'utf8');
      return JSON.parse(data);
    }
  } catch (error) {
    console.error(`❌ Error loading daily news for ${dateStr}:`, error);
  }
  
  return null;
}

// Get all unique teams from weekly users
function getAllTrackedTeams() {
  try {
    const userData = JSON.parse(fs.readFileSync('./data/users.json', 'utf8'));
    const weeklyUsers = getActiveWeeklyUsers();
    
    const allTeams = new Set();
    
    weeklyUsers.forEach(weeklyUser => {
      const user = userData.find(u => u.id === weeklyUser.userId);
      if (user && user.selectedTeams) {
        user.selectedTeams.forEach(team => allTeams.add(team));
      }
    });
    
    return Array.from(allTeams);
  } catch (error) {
    console.error('❌ Error getting tracked teams:', error);
    return [];
  }
}

// Daily news collection function
export async function collectDailyNews() {
  console.log('📰 Starting daily news collection...');
  
  const config = loadAdminConfig();
  if (!config || !config.weeklyDigestEnabled) {
    console.log('⚠️  Weekly digest system is disabled');
    return false;
  }
  
  const allTeams = getAllTrackedTeams();
  if (allTeams.length === 0) {
    console.log('⚠️  No teams to track for weekly users');
    return false;
  }
  
  console.log(`🎯 Collecting news for ${allTeams.length} teams: ${allTeams.slice(0, 3).join(', ')}${allTeams.length > 3 ? '...' : ''}`);
  
  try {
    // Group teams by sport for more efficient searching
    const teamGroups = groupTeamsBySport(allTeams);
    const teamNews = {};
    
    for (const [sport, teams] of Object.entries(teamGroups)) {
      console.log(`🔍 Searching for ${sport} news (${teams.length} teams)...`);
      
      const queries = buildSearchQueries(teams);
      const articles = await fetchMultipleQueries(queries);
      
      if (articles.length > 0) {
        const processedArticles = processArticles(articles, 'All', false); // Daily processing
        teamNews[sport] = {
          teams,
          articles: processedArticles.slice(0, 20), // Limit to top 20 per sport
          searchQueries: queries
        };
        
        console.log(`📊 ${sport}: ${processedArticles.length} articles collected`);
      }
      
      // Rate limiting between sports
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    // Save the daily collection
    const today = new Date();
    const success = saveDailyNews(today, teamNews);
    
    if (success) {
      // Update admin config with last collection time
      config.lastNewsCollection = new Date().toISOString();
      fs.writeFileSync('./data/admin.json', JSON.stringify(config, null, 2));
    }
    
    return success;
    
  } catch (error) {
    console.error('❌ Error in daily news collection:', error);
    return false;
  }
}

// Group teams by sport for efficient searching
function groupTeamsBySport(teams) {
  const sportGroups = {
    NFL: [],
    NBA: [],
    MLB: [],
    NHL: [],
    MLS: []
  };
  
  teams.forEach(team => {
    const sport = identifyTeamSport(team);
    if (sportGroups[sport]) {
      sportGroups[sport].push(team);
    }
  });
  
  // Remove empty groups
  Object.keys(sportGroups).forEach(sport => {
    if (sportGroups[sport].length === 0) {
      delete sportGroups[sport];
    }
  });
  
  return sportGroups;
}

// Identify team sport (enhanced from groqClient.js)
function identifyTeamSport(teamName) {
  const teamLower = teamName.toLowerCase();
  
  const sportKeywords = {
    NFL: ['patriots', 'eagles', 'cowboys', 'packers', 'steelers', 'ravens', 'chiefs', 'bills', 'titans', 'colts', 'texans', 'jaguars', 'broncos', 'raiders', 'chargers', 'seahawks', 'rams', 'cardinals', '49ers', 'bears', 'lions', 'vikings', 'falcons', 'panthers', 'saints', 'buccaneers', 'giants', 'jets', 'dolphins', 'browns', 'bengals', 'commanders'],
    NBA: ['lakers', 'warriors', 'celtics', 'heat', 'bulls', 'knicks', 'nets', 'sixers', '76ers', 'cavaliers', 'pistons', 'pacers', 'bucks', 'hawks', 'hornets', 'magic', 'wizards', 'raptors', 'mavericks', 'rockets', 'spurs', 'grizzlies', 'pelicans', 'thunder', 'nuggets', 'jazz', 'blazers', 'kings', 'clippers', 'suns', 'timberwolves'],
    MLB: ['yankees', 'red sox', 'dodgers', 'giants', 'cubs', 'cardinals', 'braves', 'phillies', 'mets', 'nationals', 'marlins', 'tigers', 'guardians', 'white sox', 'twins', 'royals', 'brewers', 'reds', 'pirates', 'astros', 'rangers', 'athletics', 'angels', 'mariners', 'rays', 'blue jays', 'orioles', 'diamondbacks', 'rockies', 'padres'],
    NHL: ['bruins', 'rangers', 'penguins', 'capitals', 'flyers', 'devils', 'islanders', 'sabres', 'maple leafs', 'senators', 'canadiens', 'lightning', 'panthers', 'hurricanes', 'blue jackets', 'red wings', 'blackhawks', 'blues', 'predators', 'wild', 'avalanche', 'stars', 'flames', 'oilers', 'canucks', 'kings', 'ducks', 'sharks', 'golden knights', 'kraken', 'coyotes'],
    MLS: ['galaxy', 'lafc', 'sounders', 'timbers', 'fire', 'crew', 'revolution', 'united', 'city', 'fc']
  };
  
  for (const [sport, keywords] of Object.entries(sportKeywords)) {
    if (keywords.some(keyword => teamLower.includes(keyword))) {
      return sport;
    }
  }
  
  return 'NFL'; // Default fallback
}

// Aggregate weekly news for a user
function aggregateWeeklyNews(user, weekStart) {
  const weekDays = [];
  for (let i = 0; i < 7; i++) {
    const date = new Date(weekStart);
    date.setDate(date.getDate() + i);
    weekDays.push(date);
  }
  
  let allArticles = [];
  let sourceCount = 0;
  
  weekDays.forEach(date => {
    const dailyNews = loadDailyNews(date);
    if (dailyNews && dailyNews.teamNews) {
      Object.values(dailyNews.teamNews).forEach(sportData => {
        if (sportData.articles) {
          // Filter articles relevant to user's teams
          const relevantArticles = sportData.articles.filter(article => {
            const title = article.title.toLowerCase();
            const description = (article.description || '').toLowerCase();
            const text = `${title} ${description}`;
            
            return user.selectedTeams.some(team => {
              const teamWords = team.toLowerCase().split(' ');
              return teamWords.some(word => text.includes(word));
            });
          });
          
          allArticles.push(...relevantArticles);
          sourceCount += relevantArticles.length;
        }
      });
    }
  });
  
  // Remove duplicates and sort by importance
  const uniqueArticles = removeDuplicateArticles(allArticles);
  uniqueArticles.sort((a, b) => (b.importanceScore || 0) - (a.importanceScore || 0));
  
  return {
    articles: uniqueArticles.slice(0, 15), // Top 15 articles
    totalSources: sourceCount,
    daysCollected: weekDays.length,
    weekStart: getDateString(weekStart)
  };
}

// Remove duplicate articles
function removeDuplicateArticles(articles) {
  const seen = new Set();
  return articles.filter(article => {
    const key = `${article.title}_${article.source_id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Generate weekly digest for all users
export async function generateWeeklyDigests() {
  console.log('📅 Starting weekly digest generation...');
  
  const config = loadAdminConfig();
  if (!config || !config.weeklyDigestEnabled) {
    console.log('⚠️  Weekly digest system is disabled');
    return false;
  }
  
  const weeklyUsers = getActiveWeeklyUsers();
  if (weeklyUsers.length === 0) {
    console.log('📭 No users configured for weekly digest');
    return false;
  }
  
  // Get this week's start (Sunday)
  const today = new Date();
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - today.getDay()); // Go back to Sunday
  weekStart.setHours(0, 0, 0, 0);
  
  console.log(`📊 Generating digests for ${weeklyUsers.length} users`);
  console.log(`📅 Week of ${getDateString(weekStart)}`);
  
  try {
    // Load user data
    const userData = JSON.parse(fs.readFileSync('./data/users.json', 'utf8'));
    
    for (const weeklyUser of weeklyUsers) {
      const user = userData.find(u => u.id === weeklyUser.userId);
      if (!user) {
        console.log(`⚠️  User ${weeklyUser.userId} not found, skipping`);
        continue;
      }
      
      console.log(`\n🎯 Generating digest for ${user.name} (${user.city}, ${user.state})`);
      
      // Aggregate week's news for this user
      const weeklyNews = aggregateWeeklyNews(user, weekStart);
      
      if (weeklyNews.articles.length === 0) {
        console.log(`📭 No relevant articles found for ${user.name}`);
        continue;
      }
      
      // Build digest content
      const digestContent = await buildWeeklyDigestContent(user, weeklyNews);
      
      if (digestContent) {
        // Save digest
        const filename = `${user.name.toLowerCase().replace(/\s+/g, '-')}-weekly-${getDateString(weekStart)}.txt`;
        const filepath = path.join(DIGEST_ARCHIVE_DIR, filename);
        
        fs.writeFileSync(filepath, digestContent, 'utf8');
        console.log(`✅ Digest saved: ${filepath}`);
        
        // Update user's last digest time
        updateUserLastDigest(user.id);
      } else {
        console.log(`❌ Failed to generate digest for ${user.name}`);
      }
      
      // Small delay between users
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    return true;
    
  } catch (error) {
    console.error('❌ Error generating weekly digests:', error);
    return false;
  }
}

// Build weekly digest content with snarky disclaimer
async function buildWeeklyDigestContent(user, weeklyNews) {
  try {
    // Build article text for AI processing
    let digestText = `Weekly sports digest for ${user.name} in ${user.city}, ${user.state}\n`;
    digestText += `Teams following: ${user.selectedTeams.join(', ')}\n`;
    digestText += `Week of: ${weeklyNews.weekStart}\n`;
    digestText += `Articles processed: ${weeklyNews.totalSources} → ${weeklyNews.articles.length} final\n\n`;
    
    const sources = [];
    
    for (let i = 0; i < weeklyNews.articles.length; i++) {
      const article = weeklyNews.articles[i];
      
      digestText += `${i + 1}. ${article.title}\n`;
      digestText += `Source: ${article.source_id || 'Unknown'}\n`;
      digestText += `Published: ${article.pubDate || 'This week'}\n`;
      digestText += `Importance: ${article.importanceScore || 0}/10\n`;
      digestText += `Summary: ${article.description || 'No summary available'}\n`;
      digestText += `URL: ${article.link}\n\n`;
      
      sources.push(article.link);
    }
    
    // Generate AI digest
    const groqResult = await generateDigestWithGroq(
      digestText,
      sources,
      user.city,
      user.selectedTeams,
      user.name,
      true, // isWeekly
      process.env.GROQ_API_KEY
    );
    
    if (!groqResult) {
      return null;
    }
    
    // Add snarky disclaimer and metadata
    const timestamp = new Date().toLocaleString();
    const weekIdentifier = getWeekIdentifier();
    
    const finalContent = `Generated: ${timestamp}
Week: ${weekIdentifier}
User: ${user.name} (${user.city}, ${user.state})
Teams: ${user.selectedTeams.join(', ')}
Articles analyzed: ${weeklyNews.totalSources}
Days collected: ${weeklyNews.daysCollected}
AI Model: ${groqResult.model}

${groqResult.content}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  REALITY CHECK ⚠️

This commentary was lovingly crafted by an AI that has never watched a game, never felt the agony of defeat, and thinks "offside" is a type of parking violation. It was not reviewed by anyone who knows anything about sports... or frankly, anyone at all. 

We scraped the internet for sports words, fed them to a robot, and hoped for the best. If you want to fact-check any of this nonsense before you confidently declare at Monday morning coffee that "the Colts are rebuilding their offensive strategy" (or whatever we said), here are the actual sources we stole this information from:

🔗 Sources (Use at your own conversational risk):
${sources.map((url, index) => `${index + 1}. ${url}`).join('\n')}

Remember: You're aiming for "passingly informed," not "ESPN analyst." If someone asks follow-up questions, just nod knowingly and change the subject to the weather.

—Statsworth (AI Sports Correspondent & Professional Guesser)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
    
    return finalContent;
    
  } catch (error) {
    console.error('❌ Error building weekly digest content:', error);
    return null;
  }
}

// Check if it's time to run weekly digest (Sunday at configured time)
export function shouldRunWeeklyDigest() {
  const config = loadAdminConfig();
  if (!config || !config.weeklyDigestEnabled) {
    return false;
  }
  
  const now = new Date();
  const dayOfWeek = now.getDay(); // 0 = Sunday
  const currentHour = now.getHours();
  const currentMinute = now.getMinutes();
  
  // Check if it's Sunday (or configured day)
  if (dayOfWeek !== (config.digestDay || 0)) {
    return false;
  }
  
  // Parse configured time (default "00:00")
  const [targetHour, targetMinute] = (config.digestTime || '00:00').split(':').map(Number);
  
  // Check if we're within 5 minutes of target time
  const targetTime = targetHour * 60 + targetMinute;
  const currentTime = currentHour * 60 + currentMinute;
  const timeDiff = Math.abs(currentTime - targetTime);
  
  return timeDiff <= 5; // Within 5 minutes
}

// Manual trigger for testing
export async function manualWeeklyDigest() {
  console.log('🧪 Manual weekly digest generation...');
  return await generateWeeklyDigests();
}

// Manual trigger for daily collection
export async function manualDailyCollection() {
  console.log('🧪 Manual daily news collection...');
  return await collectDailyNews();
}

// Get news pool statistics
export function getNewsPoolStats() {
  const files = fs.readdirSync(NEWS_POOL_DIR).filter(f => f.endsWith('.json'));
  
  let totalArticles = 0;
  let oldestDate = null;
  let newestDate = null;
  
  files.forEach(filename => {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(NEWS_POOL_DIR, filename), 'utf8'));
      totalArticles += data.totalArticles || 0;
      
      const date = new Date(data.date);
      if (!oldestDate || date < oldestDate) oldestDate = date;
      if (!newestDate || date > newestDate) newestDate = date;
    } catch (error) {
      console.warn(`⚠️  Could not read ${filename}`);
    }
  });
  
  return {
    daysCollected: files.length,
    totalArticles,
    oldestDate: oldestDate ? getDateString(oldestDate) : null,
    newestDate: newestDate ? getDateString(newestDate) : null,
    averagePerDay: files.length > 0 ? Math.round(totalArticles / files.length) : 0
  };
}

// Clean old news files (keep last 30 days)
export function cleanOldNewsFiles() {
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
  
  const files = fs.readdirSync(NEWS_POOL_DIR);
  let cleaned = 0;
  
  files.forEach(filename => {
    if (!filename.endsWith('.json')) return;
    
    const dateStr = filename.replace('.json', '');
    const fileDate = new Date(dateStr);
    
    if (fileDate < thirtyDaysAgo) {
      try {
        fs.unlinkSync(path.join(NEWS_POOL_DIR, filename));
        cleaned++;
      } catch (error) {
        console.warn(`⚠️  Could not delete ${filename}`);
      }
    }
  });
  
  if (cleaned > 0) {
    console.log(`🧹 Cleaned ${cleaned} old news files`);
  }
  
  return cleaned;
}

// Initialize directories on import
initializeDirectories();