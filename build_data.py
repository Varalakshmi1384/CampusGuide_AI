import json

# (name, sample_query, department, building, room, fees, time, category, online)
rows = [
("ID Card Reissue","I lost my ID card","Administrative Office","Admin Block","Room 12","₹200","3 working days","Identity",False),
("Bonafide Certificate","How do I get a Bonafide Certificate?","Academic Office","Admin Block","Room 5","Free","1 working day","Certificate",False),
("Transcript Request","What documents are needed for transcripts?","Examination Cell","Exam Block","Room 3","₹500","5 working days","Certificate",False),
("Hostel Admission","How can I apply for hostel admission?","Hostel Office","Hostel Block A","Room 1","₹1000 (advance)","7 working days","Hostel",False),
("Attendance Correction","How do I correct my attendance?","Academic Office","Admin Block","Room 6","Free","3 working days","Academic",False),
("Scholarship Application","How do I apply for scholarships?","Scholarship Cell","Admin Block","Room 9","Free","15 working days","Financial",True),
("Fee Receipt Duplicate","I lost my fee receipt","Accounts Office","Admin Block","Room 2","₹50","2 working days","Finance",False),
("Exam Revaluation","How do I apply for revaluation?","Examination Cell","Exam Block","Room 4","₹300/subject","20 working days","Academic",True),
("Migration Certificate","How to get migration certificate?","Examination Cell","Exam Block","Room 3","₹500","10 working days","Certificate",False),
("Character Certificate","How do I get a character certificate?","Academic Office","Admin Block","Room 5","Free","2 working days","Certificate",False),
("Hostel Leave Application","How do I apply for hostel leave?","Hostel Office","Hostel Block A","Room 2","Free","Same day","Hostel",True),
("Library Card Reissue","I lost my library card","Library","Library Building","Ground Floor","₹100","1 working day","Identity",False),
("Course Registration Correction","I registered for wrong course","Academic Office","Admin Block","Room 6","Free","3 working days","Academic",False),
("Fee Concession Application","How to apply for fee concession?","Accounts Office","Admin Block","Room 2","Free","10 working days","Financial",False),
("Semester Backlog Exam Form","How to apply for backlog exam?","Examination Cell","Exam Block","Room 4","₹400/subject","7 working days","Academic",True),
("Internship NOC","How do I get NOC for internship?","Placement Cell","Admin Block","Room 11","Free","3 working days","Career",False),
("Bus Pass Application","How to apply for college bus pass?","Transport Office","Transport Block","Room 1","₹1500/semester","5 working days","Transport",False),
("Hostel Room Change","I want to change my hostel room","Hostel Office","Hostel Block A","Room 1","Free","5 working days","Hostel",False),
("Degree Certificate Collection","How do I collect my degree certificate?","Examination Cell","Exam Block","Room 5","Free","On convocation","Certificate",False),
("Provisional Certificate","How to get provisional certificate?","Examination Cell","Exam Block","Room 5","₹300","5 working days","Certificate",False),
("Grievance Redressal","How do I file a complaint?","Grievance Cell","Admin Block","Room 15","Free","7 working days","Support",True),
("Anti-Ragging Complaint","How do I report ragging?","Anti-Ragging Committee","Admin Block","Room 16","Free","Immediate","Support",True),
("Medical Certificate Submission","Where do I submit medical certificate?","Academic Office","Admin Block","Room 6","Free","Same day","Academic",False),
("Sports Certificate Request","How to get sports participation certificate?","Sports Office","Sports Complex","Room 1","Free","3 working days","Certificate",False),
("Scholarship Status Check","How do I check my scholarship status?","Scholarship Cell","Admin Block","Room 9","Free","Instant","Financial",True),
("Exam Hall Ticket Download","Where do I download hall ticket?","Examination Cell","Online Portal","-","Free","Instant","Academic",True),
("Change of Branch Application","How to apply for branch change?","Academic Office","Admin Block","Room 7","Free","15 working days","Academic",False),
("Alumni Association Registration","How do I join alumni association?","Alumni Cell","Admin Block","Room 17","₹500","5 working days","Community",True),
("Duplicate Marksheet","I lost my marksheet","Examination Cell","Exam Block","Room 3","₹300","7 working days","Certificate",False),
("Hostel Mess Fee Refund","How do I get mess fee refund?","Hostel Office","Hostel Block A","Room 3","Free","10 working days","Hostel",False),
("Fee Installment Request","Can I pay fees in installments?","Accounts Office","Admin Block","Room 2","Free","5 working days","Finance",False),
("Convocation Registration","How do I register for convocation?","Examination Cell","Online Portal","-","₹1000","3 working days","Certificate",True),
("Student Insurance Claim","How do I file insurance claim?","Accounts Office","Admin Block","Room 3","Free","15 working days","Financial",False),
("Parking Permit","How to get vehicle parking permit?","Security Office","Gate Office","-","₹300/semester","2 working days","Facilities",False),
("Wi-Fi Access Request","My Wi-Fi isn't working, who do I contact?","IT Services","IT Block","Room 1","Free","Same day","Facilities",False),
("Lab Equipment Damage Report","I broke lab equipment, what do I do?","Department Office","Respective Dept Block","-","Varies","3 working days","Academic",False),
("Semester Fee Payment Issue","My fee payment failed online","Accounts Office","Admin Block","Room 2","Free","2 working days","Finance",True),
("Research Paper Approval","How do I get approval to publish a paper?","HOD Office","Respective Dept Block","-","Free","5 working days","Academic",False),
("Study Leave Application","How do I apply for study leave?","Academic Office","Admin Block","Room 6","Free","3 working days","Academic",False),
("Exam Seating Query","Where is my exam seat?","Examination Cell","Exam Block","Notice Board","Free","Instant","Academic",False),
("Placement Registration","How do I register for campus placements?","Placement Cell","Admin Block","Room 11","Free","2 working days","Career",True),
("Internal Marks Dispute","I think my internal marks are wrong","Respective Department","Dept Block","-","Free","7 working days","Academic",False),
("Hostel Warden Contact","Who is my hostel warden?","Hostel Office","Hostel Block A","Room 1","Free","Instant","Hostel",False),
("Gym / Sports Facility Access","How do I get gym access?","Sports Office","Sports Complex","Room 2","₹500/semester","2 working days","Facilities",False),
("Fee Structure Certificate","I need my fee structure for a bank loan","Accounts Office","Admin Block","Room 2","₹100","3 working days","Finance",False),
("Course Withdrawal","How do I withdraw from a course?","Academic Office","Admin Block","Room 6","Free","5 working days","Academic",False),
("Disability Support Services","What support is there for disabled students?","Student Welfare Office","Admin Block","Room 18","Free","3 working days","Support",False),
("Lost and Found","I lost my belongings on campus","Security Office","Gate Office","-","Free","Ongoing","Facilities",False),
("Event Permission Request","How do I get permission for a club event?","Student Activity Cell","Admin Block","Room 19","Free","5 working days","Community",False),
("Password Reset (Student Portal)","I can't log in to the student portal","IT Services","IT Block","Room 1","Free","Instant","Facilities",True),
]

docs_by_category = {
    "Identity": ["Self-declaration / FIR copy (if lost)", "1 passport size photo", "College ID proof"],
    "Certificate": ["Student ID card copy", "Filled application form", "Fee receipt (if applicable)"],
    "Hostel": ["Hostel allotment letter", "Parent consent (if applicable)", "Filled application form"],
    "Academic": ["Filled application form", "Supporting proof/document relevant to request"],
    "Financial": ["Income certificate (if applicable)", "Bank account details", "Filled application form"],
    "Finance": ["Fee receipt / transaction ID", "Student ID card copy"],
    "Career": ["Resume", "Filled NOC/registration form"],
    "Transport": ["Filled application form", "1 passport size photo"],
    "Support": ["Filled complaint/request form", "Any supporting evidence"],
    "Facilities": ["Filled request form", "Student ID card copy"],
    "Community": ["Filled registration form"],
}

def make_steps(name, dept, building, room, online):
    loc = "the online student portal" if online else f"{dept}, {building}{', ' + room if room != '-' else ''}"
    return [
        f"Visit {loc}",
        f"Fill and submit the '{name}' application form",
        "Attach the required documents listed above",
        "Pay the applicable fee (if any) at the counter or online",
        "Collect an acknowledgment / tracking number",
        "Receive the outcome within the stated processing time",
    ]

services = []
for i, (name, query, dept, building, room, fees, ptime, category, online) in enumerate(rows, start=1):
    dept_slug = dept.lower().replace(" ", "").replace("/", "")
    services.append({
        "id": i,
        "service_name": name,
        "sample_query": query,
        "intent": name.lower(),
        "department": dept,
        "building": building,
        "room_number": room,
        "fees": fees,
        "office_hours": "Mon-Fri, 9:30 AM - 4:30 PM" if not online else "Available 24/7 online",
        "processing_time": ptime,
        "is_online": online,
        "required_documents": docs_by_category.get(category, ["Filled application form"]),
        "procedure_steps": make_steps(name, dept, building, room, online),
        "contact_email": f"{dept_slug}@college.edu",
        "portal_link": "https://college-portal.edu/services" if online else None,
        "rejection_policy": "If your request is rejected, you will receive a reason via email/notice board. You may reapply after correcting the issue, or file a grievance with the Grievance Redressal Cell (Admin Block, Room 15).",
        "keywords": f"{name.lower()}, {category.lower()}, {dept.lower()}",
        "category": category,
        "priority": "high" if category in ("Identity", "Support") else "normal",
        "status": "active",
    })

with open("services.json", "w") as f:
    json.dump(services, f, indent=2)

print(f"Generated {len(services)} services")
