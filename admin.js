// admin.js - Standalone admin script that definitely works
import fs from 'fs';
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
    console.log('⚠️  Please change this password immediately!');
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

// Save admin config
function saveAdminConfig(config) {
  try {
    fs.writeFileSync(ADMIN_FILE, JSON.stringify(config, null, 2));
    return true;
  } catch (error) {
    console.error('Error saving admin config:', error);
    return false;
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

// Change admin password
async function changeAdminPassword() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true
  });
  
  return new Promise((resolve) => {
    rl.question('🔑 Enter new admin password: ', (newPassword) => {
      rl.question('🔑 Confirm new password: ', (confirmPassword) => {
        rl.close();
        
        if (newPassword !== confirmPassword) {
          console.log('❌ Passwords do not match');
          resolve(false);
          return;
        }
        
        if (newPassword.length < 6) {
          console.log('❌ Password must be at least 6 characters');
          resolve(false);
          return;
        }
        
        const config = loadAdminConfig();
        config.passwordHash = hashPassword(newPassword.trim());
        
        if (saveAdminConfig(config)) {
          console.log('✅ Admin password updated successfully');
          resolve(true);
        } else {
          console.log('❌ Failed to save new password');
          resolve(false);
        }
      });
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

// List all users (for selection)
function listAllUsers() {
  try {
    const userData = fs.readFileSync('./data/users.json', 'utf8');
    const users = JSON.parse(userData);
    
    if (users.length === 0) {
      console.log('📭 No users found. Create users first with the main app.');
      return [];
    }
    
    console.log('\n👥 Available Users:');
    console.log('='.repeat(50));
    
    users.forEach((user, index) => {
      console.log(`${index + 1}. ${user.name} (${user.city}, ${user.state})`);
      console.log(`   📧 ID: ${user.id}`);
      console.log(`   🏆 Teams: ${user.selectedTeams?.join(', ') || 'None'}`);
      console.log();
    });
    
    return users;
  } catch (error) {
    console.log('❌ Error loading users. Create users first with the main app.');
    return [];
  }
}

// List weekly users
function listWeeklyUsers() {
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
function addUserToWeekly(userId) {
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

// Remove user from weekly digest
function removeUserFromWeekly(userId) {
  const weeklyUsers = loadWeeklyUsers();
  const filteredUsers = weeklyUsers.filter(u => u.userId !== userId);
  
  if (filteredUsers.length === weeklyUsers.length) {
    console.log('⚠️  User not found in weekly digest list');
    return false;
  }
  
  if (saveWeeklyUsers(filteredUsers)) {
    console.log('✅ User removed from weekly digest list');
    return true;
  } else {
    console.log('❌ Failed to remove user from weekly list');
    return false;
  }
}

// Toggle weekly system
function toggleWeeklySystem() {
  const config = loadAdminConfig();
  config.weeklyDigestEnabled = !config.weeklyDigestEnabled;
  
  if (saveAdminConfig(config)) {
    const status = config.weeklyDigestEnabled ? 'ENABLED' : 'DISABLED';
    console.log(`✅ Weekly digest system ${status}`);
    return true;
  } else {
    console.log('❌ Failed to toggle weekly system');
    return false;
  }
}

// Admin dashboard
async function runAdminDashboard() {
  console.log('\n🔐 Admin Dashboard - Passingly Informed');
  console.log('='.repeat(50));
  console.log('📋 Manage weekly digest automation');
  
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
      const weeklyUsers = loadWeeklyUsers();
      
      console.log('\n👑 Admin Menu:');
      console.log(`📊 Weekly System: ${systemStatus}`);
      console.log(`👥 Weekly Users: ${weeklyUsers.length} configured`);
      console.log();
      console.log('1. List all users');
      console.log('2. List weekly digest users');
      console.log('3. Add user to weekly digest');
      console.log('4. Remove user from weekly digest');
      console.log('5. Toggle weekly digest system');
      console.log('6. Change admin password');
      console.log('7. View system status');
      console.log('8. Exit admin panel');
      
      const choice = await question('\nEnter choice (1-8): ');
      
      switch (choice) {
        case '1':
          listAllUsers();
          break;
          
        case '2':
          listWeeklyUsers();
          break;
          
        case '3':
          const users = listAllUsers();
          if (users.length > 0) {
            const userChoice = await question('\nEnter user number or ID to add: ');
            const index = parseInt(userChoice) - 1;
            let userId;
            
            if (!isNaN(index) && index >= 0 && index < users.length) {
              userId = users[index].id;
            } else {
              userId = userChoice;
            }
            
            addUserToWeekly(userId);
          }
          break;
          
        case '4':
          const weeklyUsers = listWeeklyUsers();
          if (weeklyUsers.length > 0) {
            const userChoice = await question('\nEnter user number or ID to remove: ');
            const index = parseInt(userChoice) - 1;
            let userId;
            
            if (!isNaN(index) && index >= 0 && index < weeklyUsers.length) {
              userId = weeklyUsers[index].userId;
            } else {
              userId = userChoice;
            }
            
            removeUserFromWeekly(userId);
          }
          break;
          
        case '5':
          toggleWeeklySystem();
          break;
          
        case '6':
          await changeAdminPassword();
          break;
          
        case '7':
          const stats = loadAdminConfig();
          const weeklyCount = loadWeeklyUsers().length;
          console.log('\n📊 System Status:');
          console.log('='.repeat(30));
          console.log(`Weekly Digest: ${stats.weeklyDigestEnabled ? '✅ Enabled' : '❌ Disabled'}`);
          console.log(`Weekly Users: ${weeklyCount}`);
          console.log(`Created: ${new Date(stats.createdAt).toLocaleDateString()}`);
          console.log(`Last Collection: ${stats.lastNewsCollection || 'Never'}`);
          console.log(`Digest Schedule: Sunday at ${stats.digestTime}`);
          break;
          
        case '8':
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

// Initialize and run
async function main() {
  initializeAdmin();
  await runAdminDashboard();
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}