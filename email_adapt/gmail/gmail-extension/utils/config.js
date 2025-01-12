const config = {
    development: {
      API_URL: 'http://localhost:3000',
      DEBUG: true
    },
    production: {
      API_URL: 'https://your-production-api.com',
      DEBUG: false
    }
  };
  
  const ENV = 'development';
  export default config[ENV];