
describe('Sign_in', () => {
  it('Execute test case steps', () => {
    cy.visit('https://www.freecrm.com/', { failOnStatusCode: false })

    // Test steps

    // Step 2: Step 2: 
    cy.xpath('/html/body/div[1]/header/div/nav/div[2]/div/div[2]/ul/a').scrollIntoView().click({ force: true })

    // Step 3: Step 3: 
    cy.xpath('/html/body/div[1]/div/div/form/div/div[1]/div/input').scrollIntoView().clear().type('bighneswarp@quinnox.com')

    // Step 4: Step 4: 
    cy.xpath('/html/body/div[1]/div/div/form/div/div[2]/div/input').scrollIntoView().clear().type('Crm@1234')

    // Step 5: Step 5: 
    cy.xpath('/html/body/div[1]/div/div/form/div/div[3]').scrollIntoView().click({ force: true })

    // Step 6: Step 6: 
    cy.xpath('/html/body/div[1]/div/div[1]/div[5]/a').scrollIntoView().click({ force: true })

  })
})
