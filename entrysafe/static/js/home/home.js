// Feature JS: Home Dashboard
document.addEventListener('DOMContentLoaded', function() {
  // Emergency Gate Call button feedback
  const emergencyBtn = document.querySelector('.clay-btn-coral');
  if (emergencyBtn) {
    emergencyBtn.addEventListener('click', function() {
      const confirmed = confirm("Are you sure you want to trigger an Emergency Gate Call to the Concierge?");
      if (confirmed) {
        alert("Connecting to Gatehouse Security Patrol (Ext: 0100)...");
      }
    });
  }

  // Concierge Desk button
  const conciergeBtn = document.querySelector('header button:has(.material-symbols-outlined)');
  if (conciergeBtn) {
    conciergeBtn.addEventListener('click', function() {
      console.log("Opening Concierge Desk communication modal");
    });
  }
});
