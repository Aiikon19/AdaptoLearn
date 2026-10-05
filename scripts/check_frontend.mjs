import { spawnSync } from 'node:child_process';

for (const file of ['app', 'admin', 'auth', 'domain', 'shared']) {
  const result = spawnSync(process.execPath, ['--check', `static/${file}.js`], {
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
