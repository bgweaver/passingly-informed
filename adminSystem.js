// simpleAdmin.js - Working admin system for immediate use
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import crypto from 'crypto';

const ADMIN_FILE = './data/admin.json';
const WEEKLY_USERS_FILE = './data/weekly_users.json';
const DATA_DIR = './data';

// Initialize admin system
function initializeAdmin() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  
  if (!fs.existsSync(ADMIN_FILE)) {
    const defaultPasswordHash = crypto.createHash('sha256').update('sports123').digest('hex');
    const adminConfig = {
      passwordHash: defaultPasswordHash,
      weeklyDigestEnabled: true,
      lastNewsCollection: null,
      digestDay: 0,
      digestTime: '00:00',
      createdAt: new Date().toISOString()
    };
    fs.writeFileSync(ADMIN_FILE, JSON.stringify(adminConfig, null, 2));
    console.log('🔐 Admin system initialized with default password: "sports123"');
  }
  
  if (!fs.existsSync(WEEKLY_USERS_FILE)) {
    fs.writeFileSync(WEEKLY_USERS_FILE, JSON.stringify([], null, 2));
  }
}

// Load admin config
function loadAdminConfig() {
  try {
    const data = fs.readFileSync(ADMIN_FILE, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading admin config:', error);
    return null;
  }
}

// Hash password
function hashPassword(password) {
  return crypto.createHash('sha256').update(password).digest('hex');
}

// Verify admin password
async function verifyAdminPassword() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true
  });
  
  const config = loadAdminConfig();
  if (!config) return false;
  
  return new Promise((resolve) => {
    rl.question('🔐 Enter admin password: ', (password) => {
      rl.close();
      const hashedInput = hashPassword(password.trim());
      if (hashedInput === config.passwordHash) {
        console.log('✅ Admin access granted');
        resolve(true);
      } else {
        console.log('❌ Invalid password');
        resolve(false);
      }
    });
  });
}

// Load weekly users
function loadWeeklyUsers() {
  try {
    const data = fs.readFileSync(WEEKLY_USERS_FILE, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    return [];
  }
}

// Save weekly users
function saveWeeklyUsers(users) {
  try {
    fs.writeFileSync(WEEKLY_USERS_FILE, JSON.stringify(users, null, 2));
    return true;
  } catch (error) {
    console.error('Error saving weekly users:', error);
    return false;
  }
}

// List weekly users
async function listWeeklyUsers() {
  const weeklyUsers = loadWeeklyUsers();
  
  if (weeklyUsers.length === 0) {
    console.log('📭 No users configured for weekly digest');
    return [];
  }
  
  console.log('\n📅 Weekly Digest Users:');
  console.log('='.repeat(50));
  
  // Load user data to show names
  let userData = [];
  try {
    const usersData = fs.readFileSync('./data/users.json', 'utf8');
    userData = JSON.parse(usersData);
  } catch (error) {
    console.warn('⚠️  Could not load user data for display');
  }
  
  weeklyUsers.forEach((weeklyUser, index) => {
    const user = userData.find(u => u.id === weeklyUser.userId);
    const userName = user ? `${user.name} (${user.city}, ${user.state})` : `User ID: ${weeklyUser.userId}`;
    const lastDigest = weeklyUser.lastDigestGenerated ? 
      new Date(weeklyUser.lastDigestGenerated).toLocaleDateString() : 'Never';
    const status = weeklyUser.enabled ? '✅ Enabled' : '❌ Disabled';
    
    console.log(`${index + 1}. ${userName}`);
    console.log(`   Status: ${status}`);
    console.log(`   Added: ${new Date(weeklyUser.addedAt).toLocaleDateString()}`);
    console.log(`   Last digest: ${lastDigest}`);
    console.log();
  });
  
  return weeklyUsers;
}

// Add user to weekly digest
async function addUserToWeekly(userId) {
  const weeklyUsers = loadWeeklyUsers();
  
  if (weeklyUsers.find(u => u.userId === userId)) {
    console.log('⚠️  User is already on weekly digest list');
    return false;
  }
  
  weeklyUsers.push({
    userId,
    addedAt: new Date().toISOString(),
    enabled: true,
    lastDigestGenerated: null
  });
  
  if (saveWeeklyUsers(weeklyUsers)) {
    console.log('✅ User added to weekly digest list');
    return true;
  } else {
    console.log('❌ Failed to add user to weekly list');
    return false;
  }
}

// Simple admin dashboard
export async function runAdminDashboard() {
  console.log('\n🔐 Admin Dashboard - Passingly Informed');
  console.log('='.repeat(50));
  
  const isAuthorized = await verifyAdminPassword();
  if (!isAuthorized) {
    console.log('❌ Access denied');
    return;
  }
  
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true
  });
  
  const question = (prompt) => new Promise((resolve) => {
    rl.question(prompt, (answer) => resolve(answer.trim()));
  });
  
  try {
    while (true) {
      const config = loadAdminConfig();
      const systemStatus = config.weeklyDigestEnabled ? '✅ ENABLED' : '❌ DISABLED';
      
      console.log('\n👑 Admin Menu:');
      console.log(`📊 Weekly System Status: ${systemStatus}`);
      console.log('1. List weekly digest users');
      console.log('2. Add user to weekly digest');
      console.log('3. Remove user from weekly digest');
      console.log('4. View system status');
      console.log('5. Exit admin panel');
      
      const choice = await question('\nEnter choice (1-5): ');
      
      switch (choice) {
        case '1':
          await listWeeklyUsers();
          break;
          
        case '2':
          const userIdToAdd = await question('Enter user ID to add to weekly digest: ');
          await addUserToWeekly(userIdToAdd);
          break;
          
        case '3':
          console.log('Remove user functionality - coming soon!');
          break;
          
        case '4':
          const stats = loadAdminConfig();
          console.log('\n📊 System Status:');
          console.log('='.repeat(30));
          console.log(`Weekly Digest: ${stats.weeklyDigestEnabled ? '✅ Enabled' : '❌ Disabled'}`);
          console.log(`Created: ${new Date(stats.createdAt).toLocaleDateString()}`);
          console.log(`Last Collection: ${stats.lastNewsCollection || 'Never'}`);
          break;
          
        case '5':
          console.log('\n👋 Exiting admin panel');
          rl.close();
          return;
          
        default:
          console.log('❌ Invalid choice');
      }
    }
  } catch (error) {
    console.error('❌ Error in admin dashboard:', error);
  } finally {
    rl.close();
  }
}

// Initialize on import
initializeAdmin();