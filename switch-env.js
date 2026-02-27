import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const env = process.argv[2];

if (!env) {
  console.error('Usage: node switch-env.js <env>');
  console.error('Valid environments: local, team, server');
  process.exit(1);
}

const source = path.join(__dirname, `.env.${env}`);
const dest = path.join(__dirname, '.env');
const envLocal = path.join(__dirname, '.env.local');
const envLocalBackup = path.join(__dirname, '.env.local.backup');

try {
  let sourceContent;

  // Check if source file exists
  if (fs.existsSync(source)) {
    // Read source file content
    sourceContent = fs.readFileSync(source, 'utf8');
  } else if (env === 'local' && fs.existsSync(envLocalBackup)) {
    // For local environment, if .env.local doesn't exist but backup does, use backup
    console.log('✓ .env.local not found, automatically restoring from backup');
    fs.copyFileSync(envLocalBackup, envLocal);
    sourceContent = fs.readFileSync(envLocalBackup, 'utf8');
  } else {
    throw new Error(`Source file ${source} not found`);
  }

  // Write to destination file
  fs.writeFileSync(dest, sourceContent, 'utf8');

  // Handle .env.local based on environment
  if (env === 'server') {
    // For server, remove .env.local to prevent Vite from overriding
    if (fs.existsSync(envLocal)) {
      // Backup if not already backed up
      if (!fs.existsSync(envLocalBackup)) {
        fs.copyFileSync(envLocal, envLocalBackup);
        console.log('✓ Backed up .env.local to .env.local.backup');
      }
      fs.unlinkSync(envLocal);
      console.log('✓ Removed .env.local to use server environment');
    }
  } else if (env === 'local') {
    // For local, restore .env.local if backup exists
    if (fs.existsSync(envLocalBackup) && !fs.existsSync(envLocal)) {
      fs.copyFileSync(envLocalBackup, envLocal);
      console.log('✓ Restored .env.local from backup');
    }
  }

  console.log(`✓ Successfully switched to ${env} environment`);

  // Verify the copy worked by reading the destination file
  const content = fs.readFileSync(dest, 'utf8');
  const apiUrlMatch = content.match(/VITE_API_BASE_URL=(.+)/);
  if (apiUrlMatch) {
    console.log(`✓ API Base URL set to: ${apiUrlMatch[1]}`);
  }

  // Clear Vite cache if it exists
  const viteCacheDir = path.join(__dirname, 'node_modules', '.vite');
  if (fs.existsSync(viteCacheDir)) {
    fs.rmSync(viteCacheDir, { recursive: true, force: true });
    console.log('✓ Cleared Vite cache');
  }

  if (env === 'local') {
    console.log('✓ Frontend: http://localhost:8081/');
    console.log('✓ Backend: http://localhost:5000/');
  } else if (env === 'team') {
    console.log('✓ Frontend: https://29tv5wlb-8081.inc1.devtunnels.ms/');
    console.log('✓ Backend: https://29tv5wlb-5000.inc1.devtunnels.ms/');
  } else if (env === 'server') {
    console.log('✓ Frontend: http://10.30.3.85:8081/');
    console.log('✓ Backend: http://10.30.3.85:5000/');
  }

  console.log('✓ Environment switch complete - restart any running dev servers');
} catch (err) {
  console.error(`✗ Error: Could not find .env.${env} file`);
  console.error(`Error details: ${err.message}`);
  process.exit(1);
}
