import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    baseUrl: 'https://example.com',
    viewportWidth: 1280,
    viewportHeight: 720,
    defaultCommandTimeout: 10000,
    requestTimeout: 10000,
    responseTimeout: 10000,
    video: false,
    screenshotOnRunFailure: true,
    supportFile: false,
    retries: {
      runMode: 0,
      openMode: 0
    }
  }
})
