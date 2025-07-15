// scheduler.js - Automated daily and weekly operations
import cron from 'node-cron';
import { collectDailyNews, generateWeeklyDigests, shouldRunWeeklyDigest, cleanOldNewsFiles } from './newsPool.js';
import { loadAdminConfig } from './adminSystem.js';

let dailyNewsJob = null;
let weeklyDigestJob = null;
let cleanupJob = null;

// Start the automated scheduler
export function startScheduler() {
  console.log('⏰ Starting automated scheduler...');
  
  // Daily news collection - every day at 11 PM
  dailyNewsJob = cron.schedule('0 23 * * *', async () => {
    console.log('\n🌙 Running scheduled daily news collection...');
    try {
      const success = await collectDailyNews();
      if (success) {
        console.log('✅ Daily news collection completed successfully');
      } else {
        console.log('❌ Daily news collection failed');
      }
    } catch (error) {
      console.error('❌ Error in scheduled daily news collection:', error);
    }
  }, {
    scheduled: false // Don't start immediately
  });
  
  // Weekly digest generation - every Sunday at midnight
  weeklyDigestJob = cron.schedule('0 0 * * 0', async () => {
    console.log('\n📅 Running scheduled weekly digest generation...');
    try {
      const success = await generateWeeklyDigests();
      if (success) {
        console.log('✅ Weekly digest generation completed successfully');
      } else {
        console.log('❌ Weekly digest generation failed');
      }
    } catch (error) {
      console.error('❌ Error in scheduled weekly digest generation:', error);
    }
  }, {
    scheduled: false
  });
  
  // Cleanup old files - every Sunday at 1 AM
  cleanupJob = cron.schedule('0 1 * * 0', () => {
    console.log('\n🧹 Running scheduled cleanup...');
    try {
      const cleaned = cleanOldNewsFiles();
      console.log(`✅ Cleanup completed - removed ${cleaned} old files`);
    } catch (error) {
      console.error('❌ Error in scheduled cleanup:', error);
    }
  }, {
    scheduled: false
  });
  
  // Start all jobs
  dailyNewsJob.start();
  weeklyDigestJob.start();
  cleanupJob.start();
  
  console.log('✅ Scheduler started:');
  console.log('   📰 Daily news collection: 11:00 PM every day');
  console.log('   📅 Weekly digests: Sunday at midnight');
  console.log('   🧹 Cleanup: Sunday at 1:00 AM');
}

// Stop the scheduler
export function stopScheduler() {
  console.log('⏹️  Stopping scheduler...');
  
  if (dailyNewsJob) {
    dailyNewsJob.stop();
    dailyNewsJob = null;
  }
  
  if (weeklyDigestJob) {
    weeklyDigestJob.stop();
    weeklyDigestJob = null;
  }
  
  if (cleanupJob) {
    cleanupJob.stop();
    cleanupJob = null;
  }
  
  console.log('✅ Scheduler stopped');
}

// Get scheduler status
export function getSchedulerStatus() {
  const config = loadAdminConfig();
  
  return {
    running: !!(dailyNewsJob && weeklyDigestJob && cleanupJob),
    dailyNewsEnabled: dailyNewsJob ? !dailyNewsJob.destroyed : false,
    weeklyDigestEnabled: weeklyDigestJob ? !weeklyDigestJob.destroyed : false,
    cleanupEnabled: cleanupJob ? !cleanupJob.destroyed : false,
    systemEnabled: config?.weeklyDigestEnabled || false,
    nextDaily: dailyNewsJob ? getNextRunTime('0 23 * * *') : null,
    nextWeekly: weeklyDigestJob ? getNextRunTime('0 0 * * 0') : null,
    nextCleanup: cleanupJob ? getNextRunTime('0 1 * * 0') : null
  };
}

// Calculate next run time for a cron expression
function getNextRunTime(cronExpression) {
  try {
    const task = cron.schedule(cronExpression, () => {}, { scheduled: false });
    // This is a simplified calculation - in real implementation you'd need a proper cron parser
    return 'Next scheduled run'; // Placeholder
  } catch (error) {
    return 'Unknown';
  }
}

// Manual test of scheduler components
export async function testSchedulerComponents() {
  console.log('🧪 Testing scheduler components...');
  
  console.log('\n1. Testing daily news collection...');
  try {
    const dailyResult = await collectDailyNews();
    console.log(`   Daily collection: ${dailyResult ? '✅ Success' : '❌ Failed'}`);
  } catch (error) {
    console.log(`   Daily collection: ❌ Error - ${error.message}`);
  }
  
  console.log('\n2. Testing weekly digest generation...');
  try {
    const weeklyResult = await generateWeeklyDigests();
    console.log(`   Weekly digests: ${weeklyResult ? '✅ Success' : '❌ Failed'}`);
  } catch (error) {
    console.log(`   Weekly digests: ❌ Error - ${error.message}`);
  }
  
  console.log('\n3. Testing cleanup...');
  try {
    const cleanupResult = cleanOldNewsFiles();
    console.log(`   Cleanup: ✅ Success - ${cleanupResult} files cleaned`);
  } catch (error) {
    console.log(`   Cleanup: ❌ Error - ${error.message}`);
  }
  
  console.log('\n✅ Scheduler component test completed');
}

// Run scheduler in daemon mode
export function runSchedulerDaemon() {
  console.log('🚀 Starting Passingly Informed Scheduler Daemon...');
  console.log('='.repeat(60));
  
  // Start the scheduler
  startScheduler();
  
  // Keep the process alive
  process.on('SIGINT', () => {
    console.log('\n🛑 Received SIGINT, shutting down gracefully...');
    stopScheduler();
    process.exit(0);
  });
  
  process.on('SIGTERM', () => {
    console.log('\n🛑 Received SIGTERM, shutting down gracefully...');
    stopScheduler();
    process.exit(0);
  });
  
  // Health check every hour
  const healthCheckInterval = setInterval(() => {
    const status = getSchedulerStatus();
    if (!status.running) {
      console.log('⚠️  Scheduler health check failed - attempting restart...');
      try {
        stopScheduler();
        startScheduler();
        console.log('✅ Scheduler restarted successfully');
      } catch (error) {
        console.error('❌ Failed to restart scheduler:', error);
      }
    } else {
      console.log('💚 Scheduler health check: OK');
    }
  }, 60 * 60 * 1000); // Every hour
  
  console.log('✅ Scheduler daemon is running');
  console.log('📊 Press Ctrl+C to stop gracefully');
  
  // Keep process alive
  setInterval(() => {
    // Do nothing, just keep alive
  }, 1000);
}