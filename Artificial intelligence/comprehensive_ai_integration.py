"""
Comprehensive AI Integration for BRD Test Case Generation
Unified implementation combining EnhancedAIEngine and EnhancedBRDProcessor
Provides improved test case generation using llama-3.3-70b-versatile with comprehensive details
"""

from groq import Groq
import json
import os
import traceback
from datetime import datetime

class EnhancedAIEngine:
    """
    Enhanced AI engine for comprehensive test case generation from BRD documents
    """
    
    def __init__(self, api_key="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"):
        """
        Initialize the AI engine with Groq client
        """
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"
        self.enhanced_parameters = {
            "max_tokens": 8000,      # Increased from 4000
            "temperature": 0.1,      # More deterministic
            "top_p": 0.9,           # Better quality
            "frequency_penalty": 0.2, # Reduces repetition
            "presence_penalty": 0.2   # Encourages diversity
        }
        print(f"[AI-ENGINE] Initialized with model: {self.model}")
        print(f"[AI-ENGINE] Parameters: {self.enhanced_parameters}")
    
    def generate_comprehensive_testcases(self, brd_content, project_name="", module_name=""):
        """
        Generate comprehensive test cases from BRD content
        
        Args:
            brd_content (str): The BRD document content
            project_name (str): Name of the project for context
            module_name (str): Name of the module for context
            
        Returns:
            dict: Generated test cases or error information
        """
        
        # Enhanced context-aware prompt
        context_info = ""
        if project_name and module_name:
            context_info = f"\nContext: Project '{project_name}' - Module '{module_name}'\n"
        
        enhanced_prompt = f"""
        You are a senior QA engineer with 15+ years of experience in software testing and requirements analysis. 
        Analyze the following Business Requirements Document and generate COMPREHENSIVE, DETAILED test cases.

        {context_info}
        BRD CONTENT:
        {brd_content[:8000]}

        GENERATE 8-15 DETAILED TEST CASES WITH:
        
        1. For EACH test case provide:
           - Test case name (clear, descriptive, 50+ characters)
           - Business objective and user story
           - Detailed description (200+ words explaining what, why, how)
           - Pre-conditions and assumptions
           - Post-conditions
           - Test data requirements
           - Priority (Critical/High/Medium/Low)
           - Risk level assessment
           - Estimated effort in hours
           - Suite type (smoke/sanity/regression/general/automation/development)

        2. For EACH test step provide:
           - Step number and description (100+ words)
           - Specific action to perform
           - Expected result with verification criteria
           - Test data values to use
           - Screens/pages involved
           - Potential failure scenarios
           - Recovery procedures if needed

        3. Test scenarios to include:
           - Positive path testing (happy flow)
           - Negative testing (error conditions)
           - Boundary value analysis
           - Error message validation
           - Data validation rules
           - User interface validation
           - Workflow validation
           - Data integrity checks
           - Performance thresholds
           - Security validations
           - Compatibility testing

        JSON FORMAT:
        {{
            "testcases": [
                {{
                    "name": "Test case name (50+ chars, descriptive)",
                    "description": "Detailed business description (200+ words)",
                    "priority": "Critical/High/Medium/Low",
                    "suite_type": "smoke/sanity/regression/general/automation/development",
                    "estimated_effort": "X hours",
                    "risk_level": "Critical/High/Medium/Low",
                    "preconditions": [
                        "List of pre-conditions"
                    ],
                    "postconditions": [
                        "List of post-conditions" 
                    ],
                    "test_data": [
                        "Required test data"
                    ],
                    "test_steps": [
                        {{
                            "step_no": 1,
                            "description": "Detailed step description (100+ words)",
                            "expected_result": "Specific expected outcome with verification criteria",
                            "test_data": "Specific data to use",
                            "screens": ["Screen names involved"],
                            "failure_scenarios": ["Potential failure cases"],
                            "recovery_procedures": ["Recovery steps"]
                        }}
                    ]
                }}
            ]
        }}

        Return only valid JSON format with maximum detail level. Be comprehensive and thorough.
        """

        try:
            print("[AI-ENGINE] Starting enhanced test case generation...")
            print(f"[AI-ENGINE] BRD content length: {len(brd_content)} characters")
            if project_name and module_name:
                print(f"[AI-ENGINE] Context: {project_name}/{module_name}")
            
            # Enhanced API call with improved parameters
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a senior QA engineer with 15+ years of experience. Create extremely detailed, comprehensive test cases that cover all scenarios including edge cases, error handling, and integration points. Be thorough and detailed in every aspect."
                    },
                    {
                        "role": "user", 
                        "content": enhanced_prompt
                    }
                ],
                **self.enhanced_parameters
            )

            ai_response = response.choices[0].message.content
            print(f"[AI-ENGINE] Raw response length: {len(ai_response)} characters")

            # Clean up the response to ensure it's valid JSON
            if ai_response.startswith('```json'):
                ai_response = ai_response[7:]
            if ai_response.endswith('```'):
                ai_response = ai_response[:-3]
            ai_response = ai_response.strip()

            # Parse the JSON response
            try:
                generated_data = json.loads(ai_response)
                testcase_count = len(generated_data.get('testcases', []))
                total_steps = sum(len(tc.get('test_steps', [])) for tc in generated_data.get('testcases', []))
                
                print(f"[AI-ENGINE] SUCCESS: Successfully generated {testcase_count} test cases")
                print(f"[AI-ENGINE] STATS: Total test steps: {total_steps}")
                print(f"[AI-ENGINE] MODEL: {self.model}")
                
                # Enhanced response with detailed summary
                return {
                    "success": True,
                    "testcases": generated_data.get('testcases', []),
                    "enhanced_summary": {
                        "total_testcases": testcase_count,
                        "total_test_steps": total_steps,
                        "average_steps_per_testcase": round(total_steps / testcase_count if testcase_count > 0 else 0, 1),
                        "model_used": self.model,
                        "parameters_used": self.enhanced_parameters,
                        "processing_time": datetime.now().isoformat(),
                        "complexity_score": "High" if total_steps > 50 else "Medium" if total_steps > 20 else "Low"
                    }
                }
                
            except json.JSONDecodeError as json_error:
                print(f"[AI-ENGINE] JSON parsing failed: {str(json_error)}")
                print(f"[AI-ENGINE] Response preview: {ai_response[:500]}...")
                
                # Try to extract JSON from response if it contains extra text
                json_start = ai_response.find('{')
                json_end = ai_response.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    try:
                        json_content = ai_response[json_start:json_end]
                        generated_data = json.loads(json_content)
                        print("[AI-ENGINE] Successfully extracted JSON from response")
                        return {
                            "success": True,
                            "testcases": generated_data.get('testcases', []),
                            "extracted": True,
                            "note": "JSON was extracted from mixed response"
                        }
                    except json.JSONDecodeError as extract_error:
                        print(f"[AI-ENGINE] Failed to extract JSON: {str(extract_error)}")
                        return {
                            "success": False,
                            "error": f"JSON parsing failed after extraction: {str(extract_error)}",
                            "raw_response_preview": ai_response[:500]
                        }
                else:
                    return {
                        "success": False,
                        "error": "Invalid JSON response - no JSON structure found",
                        "raw_response_preview": ai_response[:200]
                    }

        except Exception as e:
            error_details = f"AI Engine Error: {str(e)}"
            print(f"[AI-ENGINE] {error_details}")
            print(f"[AI-ENGINE] Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": error_details,
                "traceback": traceback.format_exc()
            }

# Flask Integration Helper Functions
def enhanced_generate_testcases_from_brd_api(brd_content, project_name="", module_name=""):
    """
    API-compatible function for Flask integration
    This can be called directly from your Flask endpoint
    """
    ai_engine = EnhancedAIEngine()
    return ai_engine.generate_comprehensive_testcases(brd_content, project_name, module_name)

def enhanced_generate_testcases_from_brd(user_email, brd_files, project_id, module_id, project_name="", module_name=""):
    """
    Enhanced BRD test case generation function for Flask integration
    Call this from your Flask endpoint instead of the current implementation
    """
    try:
        # Read BRD files content
        brd_content = ""
        for brd_file in brd_files:
            file_id = brd_file.get('id')
            if not file_id:
                continue

            # Get file path from database (you'll need to implement this part)
            # This is a placeholder - adapt to your database structure
            file_path = f"/path/to/brd/file_{file_id}"  # Update this
            
            if os.path.exists(file_path):
                try:
                    # Read file content based on type
                    if file_path.lower().endswith('.pdf'):
                        import PyPDF2
                        with open(file_path, 'rb') as f:
                            pdf_reader = PyPDF2.PdfReader(f)
                            for page in pdf_reader.pages:
                                brd_content += page.extract_text() + "\n"
                    elif file_path.lower().endswith('.docx'):
                        import docx
                        doc = docx.Document(file_path)
                        for para in doc.paragraphs:
                            brd_content += para.text + "\n"
                    else:
                        # For other file types, try to read as text
                        with open(file_path, 'r', encoding='utf-8') as f:
                            brd_content += f.read() + "\n"

                    brd_content += f"\n--- End of file ---\n\n"

                except Exception as e:
                    print(f"[Enhanced-BRD] Could not read file {file_path}: {str(e)}")
                    continue

        if not brd_content.strip():
            return {
                'success': False,
                'error': 'No readable content found in BRD files'
            }

        # Use enhanced AI engine
        ai_engine = EnhancedAIEngine()
        result = ai_engine.generate_comprehensive_testcases(brd_content, project_name, module_name)
        
        if result["success"]:
            return {
                'success': True,
                'message': f'Enhanced AI generated {result["enhanced_summary"]["total_testcases"]} comprehensive test cases',
                'generated_testcases': result["testcases"],
                'enhanced_summary': result["enhanced_summary"],
                'improvements': [
                    "Double token limit (8000 vs 4000)",
                    "Lower temperature (0.1 vs 0.3) for consistency",
                    "Added top_p, frequency_penalty, presence_penalty",
                    "Enhanced prompt engineering",
                    "Detailed test step descriptions",
                    "Comprehensive test coverage",
                    "Risk assessment and effort estimation"
                ]
            }
        else:
            return {
                'success': False,
                'error': result['error']
            }

    except Exception as e:
        error_details = f"Enhanced BRD processing failed: {str(e)}"
        print(f"[Enhanced-BRD] {error_details}")
        return {
            'success': False,
            'error': error_details
        }

def get_enhanced_ai_engine():
    """
    Factory function to get a configured EnhancedAIEngine instance
    """
    return EnhancedAIEngine()

# Flask endpoint example
def flask_endpoint_example():
    """
    Example of how to integrate this into your Flask endpoint
    
    NOTE: This is a demonstration function. In your actual Flask app,
    you would define your Flask app instance first, then use this pattern.
    """
    
    # Example Flask endpoint implementation:
    """
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    
    @app.route('/api/generate-testcases-from-brd-enhanced', methods=['POST'])
    def generate_testcases_from_brd_enhanced():
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        brd_files = data.get('brd_files', [])
        project_id = data.get('project_id')
        module_id = data.get('module_id')
        project_name = data.get('project_name', '')
        module_name = data.get('module_name', '')

        if not brd_files:
            return jsonify({'error': 'No BRD files selected'}), 400

        # Use enhanced BRD processor
        result = enhanced_generate_testcases_from_brd(
            user_email=user_email,
            brd_files=brd_files,
            project_id=project_id,
            module_id=module_id,
            project_name=project_name,
            module_name=module_name
        )
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    """
    pass

# Test function
def test_enhanced_ai():
    """
    Test the enhanced AI engine with sample data
    """
    print("=" * 80)
    print("[AI-TEST] Testing Comprehensive AI Integration")
    print("=" * 80)
    
    # Sample BRD content
    sample_brd = """
    Banking Application Development Requirements:

    1. User Registration & Login
    - Users can register with national ID and mobile number
    - OTP verification required for registration
    - Strong password requirements
    - Account lockout after 3 failed attempts
    - Biometric authentication support

    2. Account Management
    - View account balance and transaction history
    - Account statement download (PDF/Excel)
    - Multiple account support
    - Account nickname customization
    - Account blocking/unblocking

    3. Fund Transfer
    - Internal transfer (same bank)
    - External transfer (other banks via NEFT/RTGS/IMPS)
    - UPI payments
    - Bulk transfer from file
    - Scheduled transfers
    - Transfer limits based on KYC level

    4. Bill Payments
    - Electricity, water, gas bills
    - Mobile recharge
    - DTH recharge
    - Credit card payments
    - Insurance premium payments
    - Recurring bill setup

    5. Investment Services
    - Fixed deposit calculator
    - Loan EMI calculator
    - Investment tracking
    - Mutual fund investment (limited)
    - Gold investment

    Security Requirements:
    - Multi-factor authentication
    - Transaction PIN for sensitive operations
    - Session timeout
    - Device fingerprinting
    - Transaction monitoring

    Performance Requirements:
    - Page load time < 2 seconds
    - Support 5000 concurrent users
    - 99.95% uptime
    - Transaction processing < 5 seconds
    """
    
    ai_engine = get_enhanced_ai_engine()
    result = ai_engine.generate_comprehensive_testcases(sample_brd, "BankingApp", "CoreBanking")
    
    if result["success"]:
        print(f"[AI-TEST] SUCCESS: Generated {result['enhanced_summary']['total_testcases']} test cases")
        print(f"[AI-TEST] STATS: Total steps: {result['enhanced_summary']['total_test_steps']}")
        print(f"[AI-TEST] MODEL: {result['enhanced_summary']['model_used']}")
        print(f"[AI-TEST] COMPLEXITY: {result['enhanced_summary']['complexity_score']}")
        print(f"[AI-TEST] TIMING: Average steps per test case: {result['enhanced_summary']['average_steps_per_testcase']}")
        
        # Show sample test case details
        if result['testcases']:
            sample_tc = result['testcases'][0]
            print(f"\n[AI-TEST] Sample Test Case:")
            print(f"[AI-TEST] Name: {sample_tc['name']}")
            print(f"[AI-TEST] Priority: {sample_tc['priority']}")
            print(f"[AI-TEST] Suite Type: {sample_tc['suite_type']}")
            print(f"[AI-TEST] Risk Level: {sample_tc['risk_level']}")
            print(f"[AI-TEST] Estimated Effort: {sample_tc['estimated_effort']}")
            print(f"[AI-TEST] Steps: {len(sample_tc['test_steps'])}")
            print(f"[AI-TEST] Description length: {len(sample_tc['description'])} characters")
    else:
        print(f"[AI-TEST] ERROR: {result['error']}")
    
    print("=" * 80)
    return result

if __name__ == "__main__":
    print("=" * 80)
    print("[COMPREHENSIVE-AI] Comprehensive AI Integration for BRD Test Case Generation")
    print("=" * 80)
    print("[COMPREHENSIVE-AI] Features:")
    print("[COMPREHENSIVE-AI] * 8000 token limit (2x current)")
    print("[COMPREHENSIVE-AI] * 0.1 temperature (more consistent)")
    print("[COMPREHENSIVE-AI] * Advanced sampling parameters")
    print("[COMPREHENSIVE-AI] * Enhanced prompt engineering")
    print("[COMPREHENSIVE-AI] * Comprehensive test coverage")
    print("[COMPREHENSIVE-AI] * Detailed step descriptions")
    print("[COMPREHENSIVE-AI] * Risk assessment & effort estimation")
    print("[COMPREHENSIVE-AI] * Flask integration ready")
    print("[COMPREHENSIVE-AI] * File processing capabilities")
    print("=" * 80)
    
    # Run the comprehensive test
    test_enhanced_ai()