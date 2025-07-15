// terminalFix.js - Simple script to test and fix terminal input issues
import readline from 'readline';

function createCleanInterface() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true,
    // Explicitly set these to avoid doubling
    completer: undefined,
    historySize: 0
  });
  
  // Disable raw mode if it's enabled
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }
  
  return rl;
}

function cleanQuestion(rl, prompt) {
  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      // Clean the answer of any control characters or duplicates
      const cleaned = answer.replace(/[\x00-\x1F\x7F]/g, '').trim();
      resolve(cleaned);
    });
  });
}

async function testTerminalInput() {
  console.log('🧪 Testing terminal input fix...');
  console.log('This should help with character doubling issues.\n');
  
  const rl = createCleanInterface();
  
  try {
    console.log('Type a number (like "1") and press Enter:');
    const input1 = await cleanQuestion(rl, '> ');
    console.log(`You entered: "${input1}"`);
    
    console.log('\nType some text and press Enter:');
    const input2 = await cleanQuestion(rl, '> ');
    console.log(`You entered: "${input2}"`);
    
    console.log('\n✅ Terminal input test complete!');
    console.log('If you still see doubling, try running: stty sane');
    
  } finally {
    rl.close();
  }
}

// Export for use in main app
export { createCleanInterface, cleanQuestion };

// Run test if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  testTerminalInput();
}