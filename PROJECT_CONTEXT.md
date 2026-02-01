                                                                           
⏺ ----------------------------------------------------------------                                                      
  PROJECT: Lease Management & Renewal Assistant (Single-User MVP)                                                       
  ----------------------------------------------------------------                                                      
                                                                                                                        
  OVERVIEW                                                                                                              
  This is a local, single-user Flask web app for managing property lease documents.                                     
  The app allows uploading lease PDFs/images, extracting text via OCR, using AI                                         
  to suggest structured lease details, manually editing those details, managing                                         
  lease renewals (versions), and tracking lease expiry and rent reminders.                                              
                                                                                                                        
  The app prioritizes:                                                                                                  
  - Auditability (what AI suggested vs what user saved)                                                                 
  - Persistence (no in-memory-only critical data)                                                                       
  - Safety (confirmations before destructive actions)                                                                   
  - Beginner-friendly UI (clear flows, no hidden state)  

  ----------------------------------------------------------------
  DEVELOPMENT RULES
  ----------------------------------------------------------------

## Development Rules (MANDATORY)

The user is a complete beginner.

For ALL future work on this project:

1. Claude MUST explain changes in plain English.
2. Claude MUST show BEFORE / AFTER diffs for every change.
3. Claude MUST ask for explicit approval before modifying ANY file.
4. Claude MUST make ONE logical change at a time.
5. Claude MUST NOT automatically implement changes.
6. Claude MUST pause immediately if the user says "pause" or "stop".

Violating these rules is considered a critical error.                                                               
                                                                                                                        
  ----------------------------------------------------------------                                                      
  CORE CONCEPTS & DATA MODEL (CURRENT - AUTHORITATIVE)                                                                  
  ----------------------------------------------------------------                                                      
                                                                                                                        
  Each lease is stored as a JSON object using a NESTED STRUCTURE.                                                       
                                                                                                                        
  TOP-LEVEL LEASE OBJECT                                                                                                
  - id (uuid)                                                                                                           
  - lease_group_id (shared across renewals of the same lease)                                                           
  - version (integer, increasing with each renewal)                                                                     
  - is_current (boolean)                                                                                                
  - created_at (ISO timestamp)                                                                                          
  - updated_at (ISO timestamp)                                                                                          
                                                                                                                        
  SOURCE DOCUMENT (persisted permanently)                                                                               
  lease["source_document"] = {                                                                                          
      filename: string | null                                                                                           
      mimetype: string | null                                                                                           
      extracted_text: string | null   # FULL OCR / PDF text                                                             
      extracted_at: ISO timestamp | null                                                                                
  }                                                                                                                     
                                                                                                                        
  CURRENT VALUES (what the app actually uses)                                                                           
  lease["current_values"] = {                                                                                           
      lease_nickname                                                                                                    
      lessor_name                                                                                                       
      lessee_name                                                                                                       
      lease_start_date                                                                                                  
      lease_end_date                                                                                                    
      monthly_rent                                                                                                      
      security_deposit                                                                                                  
      rent_due_day                                                                                                      
  }                                                                                                                     
                                                                                                                        
  AI EXTRACTION (audit trail - does NOT overwrite automatically)                                                        
  lease["ai_extraction"] = {                                                                                            
      ran_at: ISO timestamp                                                                                             
      fields: {                                                                                                         
          field_name: {                                                                                                 
              value: extracted_value                                                                                    
              page: page_number (if available)                                                                          
              evidence: quoted_text (if available)                                                                      
          }                                                                                                             
      }                                                                                                                 
  }                                                                                                                     
                                                                                                                        
  Key principle:                                                                                                        
  - current_values = what is actually in force                                                                          
  - ai_extraction = suggestions + evidence only                                                                         
  - source_document = immutable reference text                                                                          
                                                                                                                        
  ----------------------------------------------------------------                                                      
  LEASE VERSIONING / RENEWALS                                                                                           
  ----------------------------------------------------------------                                                      
                                                                                                                        
  - Renewals create a NEW lease record                                                                                  
  - All versions share the same lease_group_id                                                                          
  - Only one version has is_current = true                                                                              
  - Older versions remain immutable historical records                                                                  
  - If the current version is deleted, the previous version becomes current                                             
                                                                                                                        
  Each renewal:                                                                                                         
  - Copies current_values from previous version                                                                         
  - Uses a new uploaded document (new source_document)                                                                  
  - May change ANY field (including parties, rent, dates)                                                               
                                                                                                                        
  ----------------------------------------------------------------                                                      
  UPLOAD & EXTRACTION FLOW                                                                                              
  ----------------------------------------------------------------                                                      
                                                                                                                        
  1. User uploads PDF / image                                                                                           
  2. App extracts text:                                                                                                 
     - Embedded text if available                                                                                       
     - OCR fallback if scanned                                                                                          
  3. Extracted text is saved into:                                                                                      
     lease.source_document.extracted_text                                                                               
  4. Lease record is immediately created                                                                                
  5. User is redirected to Edit Mode for that lease                                                                     
                                                                                                                        
  NO critical data is stored only in memory.                                                                            
                                                                                                                        
  ----------------------------------------------------------------                                                      
  EDIT MODE                                                                                                             
  ----------------------------------------------------------------                                                      
                                                                                                                        
  Edit Mode shows:                                                                                                      
  - Editable form bound to current_values                                                                               
  - Scrollable, read-only Extracted Text panel (full document text)                                                     
  - AI Autofill button                                                                                                  
                                                                                                                        
  AI Autofill:                                                                                                          
  - Reads from lease.source_document.extracted_text                                                                     
  - Saves results to lease.ai_extraction                                                                                
  - Does NOT overwrite current_values automatically                                                                     
  - UI may apply AI suggestions, but user remains in control                                                            
                                                                                                                        
  Even manually edited fields may be re-suggested by AI.                                                                
  The app should always indicate:                                                                                       
  - This field was previously manually edited                                                                           
  - What the previous value was                                                                                         
                                                                                                                        
  ----------------------------------------------------------------                                                      
  DASHBOARD                                                                                                             
  ----------------------------------------------------------------                                                      
                                                                                                                        
  - Landing page shows a dashboard (not a single lease)                                                                 
  - Leases are grouped by landlord (lessor_name)                                                                        
  - Each group shows cards for leases                                                                                   
  - Visual urgency indicators based on:                                                                                 
    - Lease expiry                                                                                                      
    - Rent payment status                                                                                               
  - A global alert/ticker exists summarizing urgent issues                                                              
    across all landlords at page load                                                                                   
                                                                                                                        
  ----------------------------------------------------------------                                                      
  DELETION RULES (SAFETY)                                                                                               
  ----------------------------------------------------------------                                                      
                                                                                                                        
  Any destructive action requires explicit confirmation:                                                                
  - Deleting a lease                                                                                                    
  - Deleting a lease version                                                                                            
  - Deleting a lease group                                                                                              
                                                                                                                        
  Deletion confirmations must:                                                                                          
  - Require re-typing the lease nickname                                                                                
  - Clearly explain consequences                                                                                        
                                                                                                                        
  ----------------------------------------------------------------                                                      
  MIGRATION & BACKWARD COMPATIBILITY                                                                                    
  ----------------------------------------------------------------                                                      
                                                                                                                        
  - Existing flat leases are auto-migrated on load                                                                      
  - Migration moves flat fields into current_values                                                                     
  - source_document is created even if extracted_text is missing                                                        
  - No data is silently dropped                                                                                         
                                                                                                                        
  Templates and backend must always read:                                                                               
      lease.current_values (preferred)                                                                                  
      fallback to flat structure ONLY for migrated legacy data                                                          
                                                                                                                        
  ----------------------------------------------------------------                                                      
  TECH STACK                                                                                                            
  ----------------------------------------------------------------                                                      
                                                                                                                        
  - Python (Flask)                                                                                                      
  - Jinja2 templates                                                                                                    
  - JSON file storage (single-user)                                                                                     
  - OCR: Tesseract                                                                                                      
  - PDF parsing + OCR fallback                                                                                          
  - AI: Claude (Anthropic API)                                                                                          
                                                                                                                        
  ----------------------------------------------------------------                                                      
  OPERATING RULES FOR CLAUDE (CRITICAL)                                                                                 
  ----------------------------------------------------------------                                                      
                                                                                                                        
  From this point forward:                                                                                              
  - NEVER apply code changes without explicit approval                                                                  
  - ALWAYS show BEFORE / AFTER diffs                                                                                    
  - ALWAYS explain in plain English                                                                                     
  - Treat this as a production codebase                                                                                 
  - One logical change per step                                                                                         
  - If uncertain, ASK before acting                                                                                     
                                                                                                                        
  ----------------------------------------------------------------                                                      
  END OF PROJECT CONTEXT                                                                                                
  ----------------------------------------------------------------                                                      
                                                                
