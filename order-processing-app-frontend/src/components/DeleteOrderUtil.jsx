// src/components/DeleteOrderUtil.jsx
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext'; // Assuming useAuth provides apiService
import { Link } from 'react-router-dom';
import './FormCommon.css'; // Assuming you have or will create this for common form styles

function DeleteOrderUtil() {
  const [bcOrderId, setBcOrderId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const { apiService } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!bcOrderId.trim()) {
      setError("BigCommerce Order ID is required.");
      return;
    }
    if (!/^\d+$/.test(bcOrderId.trim())) {
      setError("BigCommerce Order ID must be a number.");
      return;
    }

    setIsLoading(true);
    setMessage('');
    setError('');

    const confirmation = window.confirm(
      `Are you sure you want to permanently delete order with BigCommerce ID ${bcOrderId.trim()} and all its related data (POs, Shipments, Line Items) from the local database? This action cannot be undone.`
    );

    if (!confirmation) {
      setIsLoading(false);
      setMessage("Order deletion cancelled by user.");
      return;
    }

    try {
      const response = await apiService.delete(`/utils/order_by_bc_id/${bcOrderId.trim()}`);
      setMessage(response.message || "Order deleted successfully.");
      setBcOrderId(''); // Clear input on success
    } catch (err) {
      setError(err.data?.message || err.data?.error || err.message || "Failed to delete order.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="form-page-container">
      <Link to="/utils" className="form-back-link">&larr; Back to Utilities</Link>
      <h2>Delete Order Utility</h2>
      <p>This utility will delete an order and its related data (Purchase Orders, Shipments, Line Items) from the local application database using its BigCommerce Order ID. This does NOT affect BigCommerce.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="bcOrderId">BigCommerce Order ID:</label>
          <input
            type="text"
            id="bcOrderId"
            value={bcOrderId}
            onChange={(e) => setBcOrderId(e.target.value)}
            placeholder="Enter numeric BigCommerce Order ID"
            disabled={isLoading}
          />
        </div>

        {error && <p className="form-message error">{error}</p>}
        {message && <p className="form-message success">{message}</p>}

        <div className="form-actions center">
          <button type="submit" className="form-button danger" disabled={isLoading}>
            {isLoading ? 'Deleting...' : 'Delete Order from Local DB'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default DeleteOrderUtil;