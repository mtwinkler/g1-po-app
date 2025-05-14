// --- START OF FILE EditSupplierForm.jsx ---

import './EditSupplierForm.css'; // Import the CSS file
import { useState, useEffect } from 'react'; // Import useEffect for fetching data
import { useNavigate, useParams, Link } from 'react-router-dom'; // Import hooks and Link

function EditSupplierForm() {
  // State for form fields
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    payment_terms: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    zip: '',
    country: '',
    phone: '',
    contact_person: '',
    defaultponotes: '' // Ensure this matches your state if used
  });

  const [loading, setLoading] = useState(true); // State to track loading data
  const [submitting, setSubmitting] = useState(false); // State to track submission status
  const [error, setError] = useState(null); // State to store errors
  const [success, setSuccess] = useState(false); // State to track success

  const navigate = useNavigate(); // Hook for navigation
  const { supplierId } = useParams(); // --- NEW: Hook to get ID from URL ---

  useEffect(() => {
    const fetchSupplier = async () => {
      setLoading(true); // Ensure loading is true at the start
      setError(null);   // Clear previous errors
      // Construct the full absolute URL
      const relativePath = `/suppliers/${supplierId}`;
      const fullApiUrl = `${import.meta.env.VITE_API_BASE_URL}${relativePath}`;
      console.log("EditSupplierForm.jsx: Fetching supplier from:", fullApiUrl);

      try {
        const response = await fetch(fullApiUrl); // Use fullApiUrl

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ message: `HTTP error! Status: ${response.status}` })); // Try to parse JSON, fallback
          throw new Error(errorData.message || `HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();
        setFormData(data);
      } catch (error) {
        console.error("Error fetching supplier data for edit:", error);
        setError(error.message); // Set error message
      } finally {
        setLoading(false);
      }
    };

    if (supplierId) { // Only fetch if supplierId is present
        fetchSupplier();
    } else {
        setError("Supplier ID is missing.");
        setLoading(false);
    }

  }, [supplierId]);

  // Handle input changes (Same as SupplierForm)
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevState => ({
      ...prevState,
      [name]: value
    }));
  };

  // Handle form submission (MODIFIED for PUT request)
  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);

    // Construct the full absolute URL
    const relativePath = `/suppliers/${supplierId}`;
    const fullApiUrl = `${import.meta.env.VITE_API_BASE_URL}${relativePath}`;
    console.log("EditSupplierForm.jsx: Submitting PUT to:", fullApiUrl);

    try {
      const response = await fetch(fullApiUrl, { // Use fullApiUrl
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      const responseData = await response.json().catch(() => null); // Try to parse JSON, allow null

      if (!response.ok) {
        throw new Error(responseData?.message || `HTTP error! Status: ${response.status}`);
      }

      console.log("Supplier updated:", responseData);
      setSuccess(true);

      setTimeout(() => {
        navigate('/suppliers');
      }, 1500);

    } catch (error) {
      console.error("Error updating supplier:", error);
      setError(error.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
      return <p className="loading-message">Loading supplier data for editing...</p>;
  }

  if (error && !submitting && !formData.name) { // Show main fetch error only if form is not populated
       return <p style={{ color: 'red' }} className="error-message">Error loading supplier data: {error}</p>;
  }

  return (
    <div className="edit-supplier-form-container">
      <h2>Edit Supplier (ID: {supplierId})</h2>
      <Link to="/suppliers" className="form-back-link">Back to Suppliers List</Link>

      {submitting && <p className="form-message loading">Submitting updates...</p>}
      {error && <p style={{ color: 'red' }} className="form-message error">Error: {error}</p>}
      {success && <p style={{ color: 'green' }} className="form-message success">Supplier updated successfully!</p>}

      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="name">Name:</label>
          <input type="text" id="name" name="name" value={formData.name || ''} onChange={handleChange} required />
        </div>
        <div>
          <label htmlFor="email">Email:</label>
          <input type="email" id="email" name="email" value={formData.email || ''} onChange={handleChange} required />
        </div>
        <div>
          <label htmlFor="payment_terms">Payment Terms:</label>
          <input type="text" id="payment_terms" name="payment_terms" value={formData.payment_terms || ''} onChange={handleChange} />
        </div>
         <div>
           <label htmlFor="address_line1">Address Line 1:</label>
           <input type="text" id="address_line1" name="address_line1" value={formData.address_line1 || ''} onChange={handleChange} />
         </div>
         <div>
           <label htmlFor="address_line2">Address Line 2:</label>
           <input type="text" id="address_line2" name="address_line2" value={formData.address_line2 || ''} onChange={handleChange} />
         </div>
         <div>
           <label htmlFor="city">City:</label>
           <input type="text" id="city" name="city" value={formData.city || ''} onChange={handleChange} />
         </div>
          <div>
           <label htmlFor="state">State:</label>
           <input type="text" id="state" name="state" value={formData.state || ''} onChange={handleChange} />
         </div>
         <div>
           <label htmlFor="zip">Zip:</label>
           <input type="text" id="zip" name="zip" value={formData.zip || ''} onChange={handleChange} />
         </div>
          <div>
           <label htmlFor="country">Country:</label>
           <input type="text" id="country" name="country" value={formData.country || ''} onChange={handleChange} />
         </div>
         <div>
           <label htmlFor="phone">Phone:</label>
           <input type="text" id="phone" name="phone" value={formData.phone || ''} onChange={handleChange} />
         </div>
          <div>
           <label htmlFor="contact_person">Contact Person:</label>
           <input type="text" id="contact_person" name="contact_person" value={formData.contact_person || ''} onChange={handleChange} />
         </div>
         <div>
            <label htmlFor="defaultponotes">Default PO Notes:</label>
            <textarea id="defaultponotes" name="defaultponotes" value={formData.defaultponotes || ''} onChange={handleChange} rows="3" />
         </div>

        <button type="submit" disabled={submitting || loading}>
          {submitting ? 'Updating...' : 'Update Supplier'}
        </button>
      </form>
    </div>
  );
}

export default EditSupplierForm;
// --- END OF FILE EditSupplierForm.jsx ---