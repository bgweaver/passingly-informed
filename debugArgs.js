// debugArgs.js - Test what's happening with command line arguments
console.log('🔍 Debugging command line arguments...');
console.log('process.argv:', process.argv);
console.log('process.argv.slice(2):', process.argv.slice(2));

const args = process.argv.slice(2);
console.log('args length:', args.length);
console.log('args[0]:', args[0]);
console.log('args[0] === "admin":', args[0] === 'admin');

if (args[0] === 'admin') {
  console.log('✅ Admin argument detected correctly');
} else {
  console.log('❌ Admin argument not detected');
  console.log('Expected: "admin"');
  console.log('Actual:', JSON.stringify(args[0]));
}