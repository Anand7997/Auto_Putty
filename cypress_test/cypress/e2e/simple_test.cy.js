describe('Cypress Test Suite', () => {
  it('should execute basic cypress commands', () => {
    // Visit example.com
    cy.visit('/', { failOnStatusCode: false })
    
    // Wait for page to load
    cy.wait(1000)
    
    // Verify page loaded
    cy.get('body').should('exist')
    
    // Get the page title
    cy.title().then((title) => {
      cy.log(`Page title: ${title}`)
    })
    
    // Find all h1 elements  
    cy.get('h1').then((headings) => {
      cy.log(`Found ${headings.length} h1 elements`)
    })
    
    // Take a screenshot
    cy.screenshot('example-page')
    
    cy.log('Test completed successfully')
  })
})
