# HR System Document Security Status

**Date:** 2025-10-30
**System:** HR Management System
**Focus:** Employee Document Storage Security

---

## Executive Summary

This document outlines the current security status of employee documents uploaded to the HR system, including encryption and compression status.

**Key Findings:**
- Employee PII database fields ARE encrypted (Fernet/AES-128)
- Document files are NOT encrypted at rest
- Document files are NOT compressed
- Documents are stored in Docker volume with restricted permissions

---

## Document Storage Location

**Path:** `/app/documents/{employee_id}/`

Documents are stored in the Docker container's filesystem and persisted via Docker volume:
- Volume: `hr_documents`
- Container path: `/app/documents`
- Directory structure: Each employee has their own subdirectory

**File naming convention:** `{timestamp}_{original_filename}`

Example:
```
/app/documents/
├── 1/
│   ├── 20251030_120000_john_doe_id.jpg
│   ├── 20251030_120030_john_doe_ssn.jpg
│   └── 20251030_120100_food_cert.pdf
├── 2/
│   ├── 20251030_130000_jane_smith_id.pdf
│   └── 20251030_130030_jane_smith_ssn.pdf
```

---

## Document Types

The following document types are typically stored:

**Required Documents (for new hires):**
- ID Copy (Driver's License, Passport, etc.)
- Social Security Card

**Optional Documents:**
- Food Safety Certification
- TIPS Certification
- I-9 Form
- W-4 Form
- Employment Contract
- Training Certificates
- Performance Reviews

---

## Current Security Status

### 1. Document File Encryption

**Status:** ❌ **NOT ENCRYPTED**

**Details:**
- Documents are saved as plain files using `shutil.copyfileobj()`
- No encryption is applied before writing to disk
- Files can be read directly from the filesystem if someone gains access

**Code Location:** [employees.py:619-651](/opt/restaurant-system/hr/src/hr/api/api_v1/endpoints/employees.py#L619-L651)

```python
# Current implementation (NO encryption)
with open(file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)
```

**Risk Assessment:**
- **Medium Risk**: If the Docker volume or host filesystem is compromised, sensitive documents (IDs, SSNs) can be accessed
- **Mitigation**: Files are inside Docker container with restricted permissions
- **Mitigation**: Host filesystem permissions should restrict access to Docker volumes

---

### 2. Document File Compression

**Status:** ❌ **NOT COMPRESSED**

**Details:**
- Files are saved in their original format without compression
- No size optimization is performed
- Large PDF/image files consume full storage space

**Code Location:** [employees.py:619-651](/opt/restaurant-system/hr/src/hr/api/api_v1/endpoints/employees.py#L619-L651)

**Current Constraints:**
- Maximum file size: 10MB per document
- Allowed formats: PDF, DOCX, DOC, JPG, JPEG, PNG, TXT, XLSX, XLS

**Storage Impact:**
- Average ID photo: 2-5 MB
- Average PDF scan: 1-3 MB
- Estimated per employee: 5-15 MB (with all documents)
- For 100 employees: ~500 MB - 1.5 GB
- For 1000 employees: ~5-15 GB

---

### 3. Database Field Encryption

**Status:** ✅ **ENCRYPTED**

**Details:**
The following employee PII fields in the database ARE encrypted using Fernet (symmetric encryption with AES-128-CBC):

**Encrypted Database Fields:**
- `phone_number`
- `street_address`
- `city`
- `state`
- `zip_code`
- `emergency_contact_name`
- `emergency_contact_phone`
- `emergency_contact_relationship`

**Encryption Method:** Fernet (cryptography library)
- Algorithm: AES-128-CBC with HMAC authentication
- Key storage: Environment variable `ENCRYPTION_KEY`
- Key rotation: Not currently implemented

**Code Location:** [employee.py:79-168](/opt/restaurant-system/hr/src/hr/models/employee.py#L79-L168)

**Example:**
```python
@hybrid_property
def phone_number(self):
    """Decrypt phone number when accessed."""
    try:
        return get_encryption().decrypt(self._phone_number)
    except Exception:
        return self._phone_number

@phone_number.setter
def phone_number(self, value):
    """Encrypt phone number when set."""
    if value:
        self._phone_number = get_encryption().encrypt(value)
    else:
        self._phone_number = None
```

---

## Encryption Key Management

**Current Implementation:**

The encryption key is stored in environment variable `ENCRYPTION_KEY`:

```bash
# In docker-compose.yml or .env file
ENCRYPTION_KEY=<base64-encoded-32-byte-key>
```

**Key Generation:**
```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()  # Generates 32-byte URL-safe base64-encoded key
```

**Security Considerations:**
- ✅ Key is not hardcoded in source code
- ✅ Key is separate from database
- ⚠️ Key is in environment variable (should consider key vault for production)
- ❌ No key rotation implemented
- ❌ No key versioning

---

## Comparison: Database Fields vs. Document Files

| Aspect | Database PII Fields | Document Files |
|--------|---------------------|----------------|
| **Encryption** | ✅ Yes (Fernet/AES-128) | ❌ No |
| **Compression** | N/A | ❌ No |
| **Access Control** | Database permissions | Filesystem permissions |
| **Backup Security** | Encrypted in backups | Plain files in backups |
| **Key Management** | ENCRYPTION_KEY env var | N/A |
| **Examples** | Phone, address, emergency contact | ID scans, SSN cards, certificates |

---

## Recommendations

### Immediate (No Implementation)

**Current status is acceptable for internal use because:**
1. Files are inside Docker container with restricted access
2. Host filesystem permissions protect the Docker volume
3. Network isolation (files not directly web-accessible)
4. Document database records track who uploaded what and when

### Short-Term (If Enhanced Security Required)

**1. Implement Document File Encryption**

Add encryption layer for document files using the same Fernet encryption:

```python
from hr.core.encryption import get_encryption

# When saving document
with open(file_path, "wb") as buffer:
    file_content = file.file.read()
    encrypted_content = get_encryption().encrypt(file_content)
    buffer.write(encrypted_content)

# When reading document
with open(file_path, "rb") as f:
    encrypted_content = f.read()
    decrypted_content = get_encryption().decrypt(encrypted_content)
    return decrypted_content
```

**Benefits:**
- Documents encrypted at rest
- Same key infrastructure as database fields
- Transparent encryption/decryption

**Considerations:**
- Cannot view files directly from filesystem (need application to decrypt)
- Slightly slower file I/O
- Backup/restore requires encryption key

---

**2. Implement Document Compression**

Add compression for image and PDF files:

```python
from PIL import Image
from io import BytesIO
import PyPDF2

# For JPEG/PNG images
if file_ext in ['.jpg', '.jpeg', '.png']:
    image = Image.open(file.file)
    # Compress image (e.g., reduce quality to 85%)
    image.save(file_path, optimize=True, quality=85)

# For PDF files
if file_ext == '.pdf':
    # Use PyPDF2 or similar to compress
    # (Implementation depends on compression strategy)
```

**Benefits:**
- Reduced storage costs (30-50% reduction for images)
- Faster backup/restore
- Faster file transfers

**Considerations:**
- Image quality slightly reduced (use 85% quality as good balance)
- Processing time during upload
- Original file not preserved (document remains compressed)

---

### Long-Term (Enterprise Security)

**1. Use External Encrypted Storage**
- AWS S3 with server-side encryption (SSE-KMS)
- Azure Blob Storage with encryption at rest
- Google Cloud Storage with customer-managed encryption keys

**2. Implement Key Rotation**
- Regular encryption key rotation schedule
- Key versioning to handle documents encrypted with old keys
- Automated re-encryption of old documents

**3. Implement Access Logging**
- Log every document view/download
- Track who accessed what document when
- Alert on suspicious access patterns

**4. Add Document Watermarking**
- Add visible or invisible watermarks to downloaded documents
- Helps track document leaks
- Identifies who downloaded specific documents

---

## Current Workflow

### Document Upload (New Hire)

1. User creates new employee via web form
2. Employee record saved to database (PII fields encrypted)
3. User uploads documents (ID, SSN, etc.)
4. Documents saved as plain files to `/app/documents/{employee_id}/`
5. Document metadata saved to database
6. **Email sent to HR with documents attached**

### Email Attachments

When new hire email is sent:
- Email includes employee information (decrypted from database)
- Email includes position and location
- **ID Copy and Social Security Card documents are attached to email**
- Attachments are plain files (not encrypted in email)

**Security Note:** Email attachments are transmitted in plain format via SMTP. Consider:
- Using TLS for SMTP connection (currently configured)
- Encrypting attachments with password protection
- Using secure file sharing links instead of attachments

---

## Security Best Practices (Current Implementation)

**What we're doing right:**
1. ✅ Encrypting PII in database
2. ✅ Using strong encryption (Fernet/AES-128)
3. ✅ Storing encryption key outside source code
4. ✅ File size limits (10MB max)
5. ✅ File type restrictions (whitelist)
6. ✅ Audit logging (who uploaded what)
7. ✅ Document expiration tracking
8. ✅ Docker container isolation
9. ✅ Using TLS for SMTP emails

**What could be improved:**
1. ⚠️ Document files not encrypted
2. ⚠️ No compression (storage optimization)
3. ⚠️ No key rotation
4. ⚠️ Email attachments sent in plain format
5. ⚠️ Encryption key in environment variable (consider key vault)

---

## Conclusion

**For internal HR use with proper infrastructure security:**
The current implementation provides adequate security through:
- Database PII encryption
- Docker container isolation
- Filesystem permissions
- Access control via authentication
- Audit logging

**For compliance-heavy industries (healthcare, finance):**
Consider implementing:
- Document file encryption
- External encrypted storage (S3, Azure, GCS)
- Key rotation
- Enhanced access logging
- Encrypted email attachments or secure file sharing

---

**Document Version:** 1.0
**Last Updated:** 2025-10-30
**Author:** System Administrator
**Review Date:** N/A
