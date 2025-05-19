import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './HpeDescriptionList.css'; 
import { useAuth } from '../contexts/AuthContext'; 

function HpeDescriptionList() {
  const { currentUser, loading: authLoading, apiService } = useAuth();
  
  const [hpeMappings, setHpeMappings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(25);
  const [totalPages, setTotalPages] = useState(0);
  const [totalItems, setTotalItems] = useState(0);

  // --- Filter State (Option PN only) ---
  const [filterOptionPn, setFilterOptionPn] = useState('');
  // No more filterPoDescription state
  const [activeFilters, setActiveFilters] = useState({ page: 1 }); // Initialize with page

  const navigate = useNavigate();

  const fetchHpeMappings = useCallback(async (signal) => {
    if (!currentUser) {
      setHpeMappings([]); setLoading(false); return;
    }
    setLoading(true); setError(null);
    
    const apiPath = '/hpe-descriptions'; 
    const queryParams = {
      page: activeFilters.page || 1, 
      per_page: itemsPerPage,
    };
    // Only add filter_option_pn if it has a value in activeFilters
    if (activeFilters.optionPn && activeFilters.optionPn.trim()) {
      queryParams.filter_option_pn = activeFilters.optionPn.trim();
    }

    console.log("HpeDescriptionList.jsx: Fetching HPE mappings from:", apiPath, "with params:", queryParams);

    try {
      const responseData = await apiService.get(apiPath, queryParams, { signal }); 
      
      if (signal && signal.aborted) return;
      
      setHpeMappings(responseData.mappings || []);
      if (responseData.pagination) {
        setCurrentPage(responseData.pagination.currentPage);
        // setItemsPerPage(responseData.pagination.perPage); // Backend now dictates this, or keep frontend control? For now, let frontend control.
        setTotalItems(responseData.pagination.totalItems);
        setTotalPages(responseData.pagination.totalPages);
      } else {
        setTotalPages(0); setTotalItems(0);
      }

    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error fetching HPE description mappings:", err);
        setError(err.message || "Failed to fetch HPE description mappings.");
        setHpeMappings([]);
        setTotalPages(0); setTotalItems(0);
      }
    } finally {
      if (!signal || !signal.aborted) setLoading(false);
    }
  }, [currentUser, apiService, itemsPerPage, activeFilters]); 

  useEffect(() => {
    if (authLoading) { setLoading(true); return; }
    if (currentUser) {
      const abortController = new AbortController();
      fetchHpeMappings(abortController.signal); 
      return () => abortController.abort();
    } else {
      setHpeMappings([]); setLoading(false); setTotalPages(0); setTotalItems(0);
      setError("Please log in to view HPE Description Mappings.");
    }
  }, [currentUser, authLoading, fetchHpeMappings, activeFilters]);

  const handleApplyFilters = () => {
    setCurrentPage(1); 
    setActiveFilters({ 
      optionPn: filterOptionPn, // Only optionPn filter
      page: 1 
    });
  };
  
  const handleClearFilters = () => {
    setFilterOptionPn('');
    // No filterPoDescription to clear
    setCurrentPage(1); 
    setActiveFilters({ page: 1 }); 
  };

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages && newPage !== currentPage) {
      setCurrentPage(newPage);
      setActiveFilters(prev => ({ ...prev, page: newPage })); 
    }
  };
  
  const handleItemsPerPageChange = (e) => {
    const newItemsPerPage = parseInt(e.target.value, 10);
    setItemsPerPage(newItemsPerPage);
    setCurrentPage(1); 
    setActiveFilters(prev => ({ ...prev, page: 1 })); 
  };


  const handleRowClick = (optionPn) => {
    if (currentUser) navigate(`/admin/hpe-descriptions/edit/${encodeURIComponent(optionPn)}`);
    else setError("Please log in to edit mappings.");
  };

  const handleLinkClick = (e) => {
    if (!currentUser) { e.preventDefault(); setError("Please log in."); return; }
    e.stopPropagation(); 
  };

  if (authLoading) return <div className="list-view-container"><div className="loading-message">Loading session...</div></div>;
  if (!currentUser && !authLoading) return <div className="list-view-container"><h2>HPE PO Description Mappings</h2><div className="error-message">Please <Link to="/login">log in</Link> to view mappings.</div></div>;
  
  return (
    <div className="list-view-container">
      <h2>PO Descriptions</h2>

      <div className="controls-container add-and-filter-controls">
        <div className="filter-section">
          <input 
            type="text" 
            placeholder="Filter by Option PN..." 
            value={filterOptionPn} 
            onChange={(e) => setFilterOptionPn(e.target.value)} 
            className="filter-input"
            onKeyPress={(e) => e.key === 'Enter' && handleApplyFilters()} // Optional: Apply on Enter
          />
          {/* Removed PO Description filter input */}
          <button onClick={handleApplyFilters} className="btn btn-primary btn-sm filter-button">Apply Filter</button>
          <button onClick={handleClearFilters} className="btn btn-secondary btn-sm filter-button">Clear Filter</button>
        </div>
        <Link to="/admin/hpe-descriptions/add" className="add-new-button">Add New HPE Mapping</Link>
      </div>

      {loading && <div className="loading-message" style={{textAlign: 'center', margin: '20px'}}>Loading mappings...</div>}
      {error && <div className="error-message" style={{textAlign: 'center', margin: '20px'}}>Error: {error}</div>}

      {!loading && !error && hpeMappings.length === 0 && (
        <p className="empty-list-message">No HPE description mappings found matching your criteria. Click "Add New" to create one.</p>
      )}

      {!loading && !error && hpeMappings.length > 0 && (
        <>
          <div className="table-responsive-container">
            <table className="data-table">
              {/* ... table headers and body remain the same ... */}
              <thead>
                <tr>
                  <th>Option PN</th>
                  <th>PO Description</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {hpeMappings.map(mapping => (
                    <tr
                      key={mapping.option_pn}
                      className="clickable-row"
                      onClick={() => handleRowClick(mapping.option_pn)}
                      title={`Edit Mapping for ${mapping.option_pn}`}
                    >
                      <td data-label="Option PN">{mapping.option_pn}</td>
                      <td data-label="PO Description">{mapping.po_description}</td>
                      <td data-label="Actions">
                        <Link 
                          to={`/admin/hpe-descriptions/edit/${encodeURIComponent(mapping.option_pn)}`} 
                          onClick={handleLinkClick} 
                          className="action-link"
                        >
                          Edit
                        </Link>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {totalPages > 0 && (
            <div className="pagination-controls">
              <button onClick={() => handlePageChange(1)} disabled={currentPage === 1}>« First</button>
              <button onClick={() => handlePageChange(currentPage - 1)} disabled={currentPage === 1}>‹ Prev</button>
              <span> Page {currentPage} of {totalPages} (Total: {totalItems} items) </span>
              <button onClick={() => handlePageChange(currentPage + 1)} disabled={currentPage === totalPages}>Next ›</button>
              <button onClick={() => handlePageChange(totalPages)} disabled={currentPage === totalPages}>Last »</button>
              <select value={itemsPerPage} onChange={handleItemsPerPageChange} style={{marginLeft: '10px'}}>
                <option value="10">10/page</option>
                <option value="25">25/page</option>
                <option value="50">50/page</option>
                <option value="100">100/page</option>
              </select>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default HpeDescriptionList;
