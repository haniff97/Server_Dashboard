module.exports = {
  apps: [
    {
      name: 'homelab-dashboard',
      script: 'dashboard.py',
      args: '/mnt/nvme/Projects/dashboard/frontend/dashboard.py',
      cwd: '/mnt/nvme/Projects/dashboard/frontend',
      interpreter: 'python3',
      env_file: '/mnt/nvme/Projects/dashboard/.env',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env_file: '/mnt/nvme/Projects/dashboard/.env',
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: '/mnt/nvme/Projects/dashboard/logs/dashboard-error.log',
      out_file: '/mnt/nvme/Projects/dashboard/logs/dashboard-out.log',
      time: true
    },
    {
      name: 'mqtt-exporter',
      script: 'mqtt_exporter.py',
      args: '/mnt/nvme/Projects/dashboard/mqtt/mqtt_exporter.py',
      cwd: '/mnt/nvme/Projects/dashboard/mqtt',
      interpreter: 'python3',
      env_file: '.env',
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: '/mnt/nvme/Projects/dashboard/logs/mqtt-error.log',
      out_file: '/mnt/nvme/Projects/dashboard/logs/mqtt-out.log',
      time: true
    },
    {
      name: 'homelab-bot',
      script: 'telegram_bot.py',
      interpreter: 'python3',
      args: '/mnt/nvme/Projects/dashboard/backend/telegram_bot.py',
      cwd: '/mnt/nvme/Projects/dashboard/backend',
      interpreter: 'python3',
      env_file: '/mnt/nvme/Projects/dashboard/.env',
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env_file: '/mnt/nvme/Projects/dashboard/.env',
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: '/mnt/nvme/Projects/dashboard/logs/bot-error.log',
      out_file: '/mnt/nvme/Projects/dashboard/logs/bot-out.log',
      time: true
    }
  ]
};
