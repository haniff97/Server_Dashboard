module.exports = {
  apps: [
    {
      name: 'homelab-dashboard',
      script: '/usr/bin/python3',
      args: '/root/Projects/dashboard/frontend/dashboard.py',
      cwd: '/root/Projects/dashboard/frontend',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: '/root/Projects/dashboard/logs/dashboard-error.log',
      out_file: '/root/Projects/dashboard/logs/dashboard-out.log',
      time: true
    },
    {
      name: 'mqtt-exporter',
      script: '/usr/bin/python3',
      args: '/root/Projects/dashboard/mqtt/mqtt_exporter.py',
      cwd: '/root/Projects/dashboard/mqtt',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      env: {
        PYTHONUNBUFFERED: '1'
      },
      error_file: '/root/Projects/dashboard/logs/mqtt-error.log',
      out_file: '/root/Projects/dashboard/logs/mqtt-out.log',
      time: true
    }
  ]
};
