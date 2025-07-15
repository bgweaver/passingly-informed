// userManager.js - User profile management with team selection
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { getTeamsFromZip } from './zip_lookup.js';

const USERS_FILE = './data/users.json';
const DATA_DIR = './data';

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

// Initialize users file if it doesn't exist
if (!fs.existsSync(USERS_FILE)) {
  fs.writeFileSync(USERS_FILE, JSON.stringify([], null, 2));
}

// Load users from file
function loadUsers() {
  try {
    const data = fs.readFileSync(USERS_FILE, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading users:', error);
    return [];
  }
}

// Save users to file
function saveUsers(users) {
  try {
    fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
    return true;
  } catch (error) {
    console.error('Error saving users:', error);
    return false;
  }
}

// Get sport from team name
function getSportFromTeam(teamName) {
  const sportsMapping = {
    // NFL
    'Bills': 'NFL', 'Dolphins': 'NFL', 'Patriots': 'NFL', 'Jets': 'NFL', 'Ravens': 'NFL', 
    'Bengals': 'NFL', 'Browns': 'NFL', 'Steelers': 'NFL', 'Texans': 'NFL', 'Colts': 'NFL', 
    'Jaguars': 'NFL', 'Titans': 'NFL', 'Broncos': 'NFL', 'Chiefs': 'NFL', 'Raiders': 'NFL', 
    'Chargers': 'NFL', 'Cowboys': 'NFL', 'Giants': 'NFL', 'Eagles': 'NFL', 'Commanders': 'NFL',
    'Bears': 'NFL', 'Lions': 'NFL', 'Packers': 'NFL', 'Vikings': 'NFL', 'Falcons': 'NFL', 
    'Panthers': 'NFL', 'Saints': 'NFL', 'Buccaneers': 'NFL', 'Cardinals': 'NFL', 'Rams': 'NFL',
    'Seahawks': 'NFL', '49ers': 'NFL',
    
    // NBA
    'Hawks': 'NBA', 'Celtics': 'NBA', 'Nets': 'NBA', 'Hornets': 'NBA', 'Bulls': 'NBA', 
    'Cavaliers': 'NBA', 'Mavericks': 'NBA', 'Nuggets': 'NBA', 'Pistons': 'NBA', 'Warriors': 'NBA',
    'Rockets': 'NBA', 'Pacers': 'NBA', 'Clippers': 'NBA', 'Lakers': 'NBA', 'Grizzlies': 'NBA',
    'Heat': 'NBA', 'Bucks': 'NBA', 'Timberwolves': 'NBA', 'Pelicans': 'NBA', 'Knicks': 'NBA',
    'Thunder': 'NBA', 'Magic': 'NBA', '76ers': 'NBA', 'Suns': 'NBA', 'Blazers': 'NBA',
    'Kings': 'NBA', 'Spurs': 'NBA', 'Jazz': 'NBA', 'Raptors': 'NBA', 'Wizards': 'NBA',
    
    // MLB
    'Braves': 'MLB', 'Marlins': 'MLB', 'Mets': 'MLB', 'Phillies': 'MLB', 'Nationals': 'MLB',
    'Cubs': 'MLB', 'Reds': 'MLB', 'Brewers': 'MLB', 'Pirates': 'MLB', 'Cardinals': 'MLB',
    'Diamondbacks': 'MLB', 'Rockies': 'MLB', 'Dodgers': 'MLB', 'Padres': 'MLB', 'Giants': 'MLB',
    'Orioles': 'MLB', 'Red Sox': 'MLB', 'Yankees': 'MLB', 'Rays': 'MLB', 'Blue Jays': 'MLB',
    'White Sox': 'MLB', 'Guardians': 'MLB', 'Tigers': 'MLB', 'Royals': 'MLB', 'Twins': 'MLB',
    'Astros': 'MLB', 'Angels': 'MLB', 'Athletics': 'MLB', 'Mariners': 'MLB', 'Rangers': 'MLB',
    
    // NHL
    'Bruins': 'NHL', 'Sabres': 'NHL', 'Red Wings': 'NHL', 'Panthers': 'NHL', 'Canadiens': 'NHL',
    'Senators': 'NHL', 'Lightning': 'NHL', 'Maple Leafs': 'NHL', 'Hurricanes': 'NHL', 
    'Blue Jackets': 'NHL', 'Devils': 'NHL', 'Islanders': 'NHL', 'Rangers': 'NHL', 'Flyers': 'NHL',
    'Penguins': 'NHL', 'Capitals': 'NHL', 'Blackhawks': 'NHL', 'Avalanche': 'NHL', 'Stars': 'NHL',
    'Wild': 'NHL', 'Predators': 'NHL', 'Blues': 'NHL', 'Flames': 'NHL', 'Oilers': 'NHL',
    'Kraken': 'NHL', 'Canucks': 'NHL', 'Ducks': 'NHL', 'Kings': 'NHL', 'Sharks': 'NHL',
    'Golden Knights': 'NHL', 'Coyotes': 'NHL',
    
    // MLS
    'United': 'MLS', 'FC': 'MLS', 'City': 'MLS', 'Galaxy': 'MLS', 'Sounders': 'MLS',
    'Timbers': 'MLS', 'Fire': 'MLS', 'Crew': 'MLS', 'Revolution': 'MLS', 'Impact': 'MLS'
  };
  
  // Try to match the team name with sport
  for (const [keyword, sport] of Object.entries(sportsMapping)) {
    if (teamName.includes(keyword)) {
      return sport;
    }
  }
  
  // Fallback based on common patterns
  if (teamName.includes('FC') || teamName.includes('United') || teamName.includes('City SC')) {
    return 'MLS';
  }
  
  return 'Unknown';
}

// Check what season it is for prioritization
function getCurrentSeason() {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-12
  
  const seasons = {
    NFL: (month >= 9 && month <= 12) || month === 1, // Sep-Jan
    NBA: (month >= 10 && month <= 4), // Oct-Apr  
    MLB: (month >= 3 && month <= 10), // Mar-Oct
    NHL: (month >= 10 && month <= 4), // Oct-Apr
    MLS: (month >= 2 && month <= 11), // Feb-Nov
  };
  
  return seasons;
}

// Interactive team selection
async function selectTeamsInteractively(suggestedTeams, rl) {
  console.log('\n🏆 Team Selection');
  console.log('=' .repeat(40));
  
  const currentSeasons = getCurrentSeason();
  
  // Categorize teams by sport and season
  const teamsBySport = {};
  suggestedTeams.forEach(team => {
    const sport = getSportFromTeam(team);
    if (!teamsBySport[sport]) {
      teamsBySport[sport] = [];
    }
    teamsBySport[sport].push(team);
  });
  
  console.log('📋 Available teams by sport (⭐ = currently in season):');
  Object.entries(teamsBySport).forEach(([sport, teams]) => {
    const inSeason = currentSeasons[sport] ? '⭐' : '📅';
    console.log(`\n${inSeason} ${sport}:`);
    teams.forEach((team, index) => {
      console.log(`   ${index + 1}. ${team}`);
    });
  });
  
  console.log('\n🎯 You can select up to 5 teams total.');
  console.log('💡 Tip: In-season teams (⭐) will have more frequent news.');
  
  const selectedTeams = [];
  
  while (selectedTeams.length < 5) {
    const remaining = 5 - selectedTeams.length;
    const prompt = `\nEnter team name (${remaining} remaining) or 'done' to finish: `;
    const input = await question(rl, prompt);
    
    if (input.toLowerCase() === 'done') {
      break;
    }
    
    // Find matching team (case insensitive, partial match)
    const matchedTeam = suggestedTeams.find(team => 
      team.toLowerCase().includes(input.toLowerCase()) ||
      input.toLowerCase().includes(team.toLowerCase())
    );
    
    if (matchedTeam) {
      if (selectedTeams.includes(matchedTeam)) {
        console.log(`⚠️  You already selected ${matchedTeam}`);
      } else {
        selectedTeams.push(matchedTeam);
        const sport = getSportFromTeam(matchedTeam);
        const inSeason = currentSeasons[sport] ? '⭐ (in season)' : '📅 (off season)';
        console.log(`✅ Added: ${matchedTeam} - ${sport} ${inSeason}`);
      }
    } else {
      console.log(`❌ Team not found. Try: ${suggestedTeams.slice(0, 3).join(', ')}...`);
    }
  }
  
  return selectedTeams;
}

// Helper function for readline prompts
function question(rl, prompt) {
  return new Promise((resolve) => rl.question(prompt, resolve));
}

// Create new user
export async function createUser() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });
  
  try {
    console.log('\n👤 Create New User Profile');
    console.log('=' .repeat(40));
    
    const name = await question(rl, 'Enter your name: ');
    const zipCode = await question(rl, 'Enter your ZIP code: ');
    
    console.log('\n🔍 Looking up teams in your area...');
    const zipResult = await getTeamsFromZip(zipCode);
    
    if (!zipResult) {
      console.log('❌ Could not find teams for that ZIP code.');
      return null;
    }
    
    const { city, state, teams: suggestedTeams } = zipResult;
    console.log(`📍 Found: ${city}, ${state}`);
    console.log(`🏈 Suggested teams: ${suggestedTeams.join(', ')}`);
    
    const selectedTeams = await selectTeamsInteractively(suggestedTeams, rl);
    
    if (selectedTeams.length === 0) {
      console.log('❌ No teams selected. User creation cancelled.');
      return null;
    }
    
    const user = {
      id: Date.now().toString(),
      name,
      zipCode,
      city,
      state,
      selectedTeams,
      suggestedTeams,
      createdAt: new Date().toISOString(),
      lastDigestDate: null
    };
    
    // Save user
    const users = loadUsers();
    users.push(user);
    
    if (saveUsers(users)) {
      console.log('\n✅ User profile created successfully!');
      console.log(`📊 Profile: ${name} in ${city}, ${state}`);
      console.log(`🏆 Following: ${selectedTeams.join(', ')}`);
      return user;
    } else {
      console.log('❌ Failed to save user profile.');
      return null;
    }
    
  } catch (error) {
    console.error('❌ Error creating user:', error);
    return null;
  } finally {
    rl.close();
  }
}

// List all users
export function listUsers() {
  const users = loadUsers();
  
  if (users.length === 0) {
    console.log('📭 No users found. Create a user first!');
    return [];
  }
  
  console.log('\n👥 Saved Users:');
  console.log('=' .repeat(50));
  
  users.forEach((user, index) => {
    const teamCount = user.selectedTeams?.length || 0;
    const lastDigest = user.lastDigestDate ? 
      new Date(user.lastDigestDate).toLocaleDateString() : 'Never';
    
    console.log(`${index + 1}. ${user.name} (${user.city}, ${user.state})`);
    console.log(`   📧 ID: ${user.id}`);
    console.log(`   🏆 Teams: ${teamCount} selected`);
    console.log(`   📅 Last digest: ${lastDigest}`);
    console.log(`   🏈 Following: ${user.selectedTeams?.join(', ') || 'None'}`);
    console.log();
  });
  
  return users;
}

// Get user by ID
export function getUserById(id) {
  const users = loadUsers();
  return users.find(user => user.id === id);
}

// Update user's last digest date
export function updateUserDigestDate(userId) {
  const users = loadUsers();
  const userIndex = users.findIndex(user => user.id === userId);
  
  if (userIndex !== -1) {
    users[userIndex].lastDigestDate = new Date().toISOString();
    return saveUsers(users);
  }
  
  return false;
}

// Delete user
export function deleteUser(id) {
  const users = loadUsers();
  const filteredUsers = users.filter(user => user.id !== id);
  
  if (filteredUsers.length < users.length) {
    return saveUsers(filteredUsers);
  }
  
  return false;
}

// Interactive user selection
export async function selectUser() {
  const users = listUsers();
  
  if (users.length === 0) {
    return null;
  }
  
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true
  });
  
  try {
    const choice = await question(rl, '\nEnter user number or ID: ');
    
    // Clean the input to handle any terminal weirdness
    const cleanChoice = choice.trim();
    
    // Try to parse as number first (for list index)
    const index = parseInt(cleanChoice) - 1;
    if (!isNaN(index) && index >= 0 && index < users.length) {
      console.log(`✅ Selected: ${users[index].name}`);
      return users[index];
    }
    
    // Try to find by ID
    const userById = getUserById(cleanChoice);
    if (userById) {
      console.log(`✅ Selected: ${userById.name}`);
      return userById;
    }
    
    // Try partial name matching
    const nameMatch = users.find(user => 
      user.name.toLowerCase().includes(cleanChoice.toLowerCase())
    );
    if (nameMatch) {
      console.log(`✅ Selected: ${nameMatch.name} (matched by name)`);
      return nameMatch;
    }
    
    console.log(`❌ User not found. Available options: 1-${users.length} or user ID`);
    return null;
    
  } catch (error) {
    console.error('❌ Error selecting user:', error);
    return null;
  } finally {
    rl.close();
  }
}