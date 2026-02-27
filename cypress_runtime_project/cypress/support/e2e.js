import 'cypress-xpath'

Cypress.Commands.add('xpathOrCSS', (selector, isXPath = true) => {
  if (isXPath) {
    return cy.xpath(selector)
  } else {
    return cy.get(selector)
  }
})

Cypress.on('uncaught:exception', (err, runnable) => {
  return false
})
