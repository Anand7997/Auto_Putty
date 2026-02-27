import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    viewportWidth: 1280,
    viewportHeight: 720,
    defaultCommandTimeout: 8000,
    requestTimeout: 8000,
    responseTimeout: 8000,
    pageLoadTimeout: 30000,
    taskTimeout: 5000,
    video: false,
    screenshotOnRunFailure: true,
    supportFile: 'cypress/support/e2e.js',
    chromeWebSecurity: false,
    retries: {
      runMode: 0,
      openMode: 0
    },
    protocolVersion: 3,
    numTestsKeptInMemory: 10
  }
})
