import sys
import requests, base64


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    # Test 1: Pneumonia X-ray
    with open('execution/frontend/assets/sample_xray.png', 'rb') as f:
        img_b64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

    r1 = requests.post('http://localhost:8000/api/claims/submit', json={
        'raw_text': 'Patient presents with persistent cough and fever for 5 days. Prescribed Amoxicillin 500mg.',
        'evidence_attached': True, 'bill_attached': True, 'evidence_base64': img_b64,
        'patient_name': 'Siti Nurhaliza binti Mohd', 'patient_ic': '900215-14-3456', 'clinic_name': 'Klinik Famili Ampang',
        'visit_date': '2026-04-01', 'total_amount_myr': 120.0
    }, timeout=180)
    r1.raise_for_status()
    cid1 = r1.json()['claim_id']
    print('Claim submitted, id:', cid1)

    r2 = requests.get(f'http://localhost:8000/api/claims/{cid1}', timeout=180)
    d = r2.json()
    print('--- PNEUMONIA TEST ---')
    print('Status:', d.get('status'))


if __name__ == "__main__":
    main()
