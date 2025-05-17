// src/components/StandaloneUpsLabel.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext'; // For apiService
import './StandaloneUpsLabel.css'; // We'll create this CSS file

const StandaloneUpsLabel = () => {
  const { apiService } = useAuth();
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    shipToName: '',
    shipToAttentionName: '',
    shipToPhone: '',
    shipToAddress1: '',
    shipToAddress2: '',
    shipToCity: '',
    shipToState: '',
    shipToZip: '',
    shipToCountry: 'US', // Default to US
    packageWeight: '',
    packageDescription: '', // For email content
    shippingMethod: 'UPS Ground', // Default shipping method
  });

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const shippingOptions = [
    { value: 'UPS Ground', label: 'UPS Ground' },
    { value: 'UPS Next Day Air', label: 'UPS Next Day Air' },
    { value: 'UPS Next Day Air Early A.M.', label: 'UPS Next Day Air Early A.M.' },
    { value: 'UPS 2nd Day Air', label: 'UPS 2nd Day Air' },
    { value: 'UPS Worldwide Expedited', label: 'UPS Worldwide Expedited' },
    // Add more as needed, ensure these match what shipping_service.py expects
  ];

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    setSuccessMessage('');

    const payload = {
      ship_to: {
        name: formData.shipToName,
        attention_name: formData.shipToAttentionName,
        phone: formData.shipToPhone,
        address_line1: formData.shipToAddress1,
        address_line2: formData.shipToAddress2,
        city: formData.shipToCity,
        state: formData.shipToState,
        zip_code: formData.shipToZip,
        country_code: formData.shipToCountry,
      },
      package: {
        weight_lbs: parseFloat(formData.packageWeight),
        description: formData.packageDescription,
      },
      shipping_method_name: formData.shippingMethod,
    };

    try {
      const response = await apiService.post('/utils/generate_standalone_ups_label', payload);
      // 'response' here IS the JSON object: { message: "...", tracking_number: "..." }
      setSuccessMessage(`Label generated successfully! Tracking: ${response.tracking_number}`); 
    } catch (err) {
      console.error("Error generating standalone label:", err);
      // err.data should contain the JSON error from the backend if it was a JSON error response
      setError(err.data?.error || err.data?.message || err.message || 'Failed to generate label. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="standalone-label-container card">
      <h2>Standalone UPS Label Generator</h2>
      <form onSubmit={handleSubmit} className="standalone-label-form">
        
        <div className="form-section">
          <h3>Ship To Information</h3>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="shipToName">Company/Name *</label>
              <input type="text" id="shipToName" name="shipToName" value={formData.shipToName} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label htmlFor="shipToAttentionName">Attention To *</label>
              <input type="text" id="shipToAttentionName" name="shipToAttentionName" value={formData.shipToAttentionName} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label htmlFor="shipToPhone">Phone *</label>
              <input type="tel" id="shipToPhone" name="shipToPhone" value={formData.shipToPhone} onChange={handleChange} required />
            </div>
            <div className="form-group full-width">
              <label htmlFor="shipToAddress1">Address Line 1 *</label>
              <input type="text" id="shipToAddress1" name="shipToAddress1" value={formData.shipToAddress1} onChange={handleChange} required />
            </div>
            <div className="form-group full-width">
              <label htmlFor="shipToAddress2">Address Line 2</label>
              <input type="text" id="shipToAddress2" name="shipToAddress2" value={formData.shipToAddress2} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label htmlFor="shipToCity">City *</label>
              <input type="text" id="shipToCity" name="shipToCity" value={formData.shipToCity} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label htmlFor="shipToState">State/Province *</label>
              <input type="text" id="shipToState" name="shipToState" value={formData.shipToState} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label htmlFor="shipToZip">Zip/Postal Code *</label>
              <input type="text" id="shipToZip" name="shipToZip" value={formData.shipToZip} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label htmlFor="shipToCountry">Country Code *</label>
              <input type="text" id="shipToCountry" name="shipToCountry" value={formData.shipToCountry} onChange={handleChange} maxLength="2" required />
            </div>
          </div>
        </div>

        <div className="form-section">
          <h3>Package & Shipping Information</h3>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="packageWeight">Weight (lbs) *</label>
              <input type="number" id="packageWeight" name="packageWeight" value={formData.packageWeight} onChange={handleChange} step="0.1" min="0.1" required />
            </div>
            <div className="form-group">
              <label htmlFor="shippingMethod">Shipping Method *</label>
              <select id="shippingMethod" name="shippingMethod" value={formData.shippingMethod} onChange={handleChange} required>
                {shippingOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
             <div className="form-group full-width">
              <label htmlFor="packageDescription">Package Description (for email content) *</label>
              <textarea id="packageDescription" name="packageDescription" value={formData.packageDescription} onChange={handleChange} rows="2" required />
            </div>
          </div>
        </div>
        
        <button type="submit" className="btn btn-primary btn-gradient btn-shadow-lift" disabled={isLoading}>
          {isLoading ? 'Generating...' : 'Generate & Email Label'}
        </button>

        {error && <p className="error-message form-message">{error}</p>}
        {successMessage && <p className="success-message form-message">{successMessage}</p>}
      </form>
    </div>
  );
};

export default StandaloneUpsLabel;