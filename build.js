const fs = require('fs');
const path = require('path');

// Target public directory
const publicDir = path.join(__dirname, 'public');
const frontendDir = path.join(__dirname, 'frontend');

console.log('Starting static build process...');

// Ensure public directory exists (clear it if it does)
if (fs.existsSync(publicDir)) {
  fs.rmSync(publicDir, { recursive: true, force: true });
}
fs.mkdirSync(publicDir, { recursive: true });

// Read all items in the frontend directory
const items = fs.readdirSync(frontendDir);

for (const item of items) {
  const srcPath = path.join(frontendDir, item);
  const destPath = path.join(publicDir, item);
  
  // Copy everything recursively
  fs.cpSync(srcPath, destPath, { recursive: true });
  console.log(`Copied ${item} to public/`);
}

console.log('Build complete. Files are in public/');
