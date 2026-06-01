<template>
    <div class="auth-container">
      <!-- Animated background elements -->
      <div class="background-animation">
        <div class="wave wave1"></div>
        <div class="wave wave2"></div>
        <div class="wave wave3"></div>
        <div class="wave wave4"></div>
        <div class="particle-container">
          <div v-for="n in 30" :key="n" class="particle" :style="getRandomParticleStyle()"></div>
        </div>
      </div>
      
      <div class="auth-wrapper">
        <div class="auth-card">
          <h2 class="auth-heading">Reset Your Password</h2>
          
          <!-- Token validity alert -->
          <div v-if="tokenError" class="auth-alert error">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ tokenError }}</span>
          </div>
          
          <!-- Success message -->
          <div v-if="resetSuccess" class="auth-alert success">
            <i class="fas fa-check-circle"></i>
            <span>{{ successMessage }}</span>
            <div class="auth-redirect" style="margin-top: 15px;">
              <router-link to="/login" class="sign-btn">Go to Login</router-link>
            </div>
          </div>
          
          <!-- Alert for displaying errors -->
          <div v-if="errorMessage && !tokenError" class="auth-alert error">
            <i class="fas fa-exclamation-circle"></i>
            <span>{{ errorMessage }}</span>
            <button class="alert-close" @click="clearError" aria-label="Close alert">
              <i class="fas fa-times"></i>
            </button>
          </div>
          
          <form v-if="!tokenError && !resetSuccess" @submit.prevent="handleResetPassword">
            <div class="form-group">
              <label for="password" class="form-label">New Password</label>
              <div class="password-wrapper">
                <input 
                  :type="showPassword ? 'text' : 'password'" 
                  class="custom-form-control" 
                  id="password" 
                  v-model="password"
                  placeholder="Enter new password" 
                  :disabled="isLoading"
                  required
                >
                <span 
                  class="toggle-password" 
                  @click="showPassword = !showPassword"
                >
                  <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                </span>
              </div>
              <div class="password-strength" v-if="password">
                <div class="strength-meter">
                  <div 
                    class="strength-bar" 
                    :style="{ width: passwordStrength.score * 25 + '%', 
                    backgroundColor: passwordStrength.color }"
                  ></div>
                </div>
                <span class="strength-text" :style="{ color: passwordStrength.color }">
                  {{ passwordStrength.message }}
                </span>
              </div>
            </div>
            
            <div class="form-group">
              <label for="confirm_password" class="form-label">Confirm Password</label>
              <div class="password-wrapper">
                <input 
                  :type="showConfirmPassword ? 'text' : 'password'" 
                  class="custom-form-control" 
                  id="confirm_password" 
                  v-model="confirmPassword"
                  placeholder="Confirm new password" 
                  :disabled="isLoading"
                  required
                >
                <span 
                  class="toggle-password" 
                  @click="showConfirmPassword = !showConfirmPassword"
                >
                  <i :class="showConfirmPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                </span>
              </div>
              <div class="password-match" v-if="password && confirmPassword">
                <span v-if="password === confirmPassword" style="color: var(--success-color)">
                  <i class="fas fa-check"></i> Passwords match
                </span>
                <span v-else style="color: var(--error-color)">
                  <i class="fas fa-times"></i> Passwords do not match
                </span>
              </div>
            </div>
            
            <button 
              type="submit" 
              class="sign-btn" 
              :disabled="isLoading || !isFormValid"
            >
              <span v-if="isLoading"><i class="fas fa-spinner fa-spin"></i> Resetting...</span>
              <span v-else>Reset Password</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  </template>
  
  <script setup>
  import { ref, computed, onMounted } from 'vue';
  import { useRoute, useRouter } from 'vue-router';
  import axios from 'axios';
  
  const route = useRoute();
  const router = useRouter();
  
  const password = ref('');
  const confirmPassword = ref('');
  const showPassword = ref(false);
  const showConfirmPassword = ref(false);
  const isLoading = ref(false);
  const errorMessage = ref('');
  const tokenError = ref('');
  const resetSuccess = ref(false);
  const successMessage = ref('');
  const token = ref('');
  
  // Compute password strength
  const passwordStrength = computed(() => {
    if (!password.value) {
      return { score: 0, message: '', color: '#ddd' };
    }
    
    let score = 0;
    let message = 'Very weak';
    let color = '#dc3545'; // red
  
    // Check length
    if (password.value.length >= 8) score++;
    if (password.value.length >= 12) score++;
  
    // Check for numbers
    if (/\d/.test(password.value)) score++;
  
    // Check for special characters
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password.value)) score++;
    
    // Check for uppercase and lowercase
    if (/[A-Z]/.test(password.value) && /[a-z]/.test(password.value)) score++;
  
    // Define messages and colors based on score
    if (score === 1) {
      message = 'Weak';
      color = '#dc3545'; // red
    } else if (score === 2) {
      message = 'Fair';
      color = '#ffc107'; // yellow
    } else if (score === 3) {
      message = 'Good';
      color = '#17a2b8'; // teal
    } else if (score >= 4) {
      message = 'Strong';
      color = '#28a745'; // green
    }
  
    return { score, message, color };
  });
  
  // Computed property to check if form is valid
  const isFormValid = computed(() => {
    return (
      password.value.length >= 8 && 
      password.value === confirmPassword.value && 
      passwordStrength.value.score >= 2 // At least "Fair" strength
    );
  });
  
  // Clear error state
  const clearError = () => {
    errorMessage.value = '';
  };
  
  // Check token validity function
  const checkTokenValidity = async (token) => {
    try {
      // This just checks if the token can be used, without actually resetting the password
      await axios.post('/api/accounts/password-reset-confirm/', {
        token: token,
        validate_only: true // This would be a backend feature to only validate the token
      });
      return true;
    } catch (error) {
      if (error.response && error.response.status === 400) {
        tokenError.value = error.response.data.error || 'This password reset link is invalid or has expired.';
      } else {
        tokenError.value = 'Unable to validate your reset token. Please request a new password reset link.';
      }
      return false;
    }
  };
  
  // Handle form submission
  const handleResetPassword = async () => {
    if (!isFormValid.value) {
      errorMessage.value = 'Please make sure your passwords match and are sufficiently strong.';
      return;
    }
    
    isLoading.value = true;
    errorMessage.value = '';
    
    try {
      const response = await axios.post('/api/accounts/password-reset-confirm/', {
        token: token.value,
        password: password.value
      });
      
      // Display success message
      resetSuccess.value = true;
      successMessage.value = response.data.message || 'Your password has been reset successfully';
      
    } catch (error) {
      if (error.response && error.response.data) {
        errorMessage.value = error.response.data.error || 'An error occurred. Please try again.';
        
        // Check if token was rejected
        if (error.response.status === 400 && error.response.data.error.includes('token')) {
          tokenError.value = error.response.data.error;
        }
      } else {
        errorMessage.value = 'Network error. Please check your connection and try again.';
      }
    } finally {
      isLoading.value = false;
    }
  };
  
  // Get random particle style
  const getRandomParticleStyle = () => {
    return {
      width: Math.floor(Math.random() * 7.2 + 1.8) + 'px',
      height: Math.floor(Math.random() * 7.2 + 1.8) + 'px',
      left: Math.floor(Math.random() * 100) + '%',
      top: Math.floor(Math.random() * 100) + '%',
      animationDelay: Math.random() * 8 + 's',
      animationDuration: Math.floor(Math.random() * 18 + 27) + 's',
      opacity: Math.random() * 0.45 + 0.09
    };
  };
  
  onMounted(async () => {
    // Get token from URL
    token.value = route.query.token;
    
    if (!token.value) {
      tokenError.value = 'No reset token provided. Please use the link from your email.';
      return;
    }
    
    // Optional: Validate token on component mount
    // await checkTokenValidity(token.value);
    
    // Use jQuery for animations
    $(document).ready(function() {
      $('.custom-form-control').focus(function() {
        $(this).addClass('focus-active');
      }).blur(function() {
        $(this).removeClass('focus-active');
      });
      
      $('.auth-card').addClass('animate-in');
    });
  });
  </script>
  
  <style scoped>
  /* Reuse the CSS from the login component, and add these styles */
  
  .password-strength {
    margin-top: 9px;
    font-size: var(--fs-xs);
  }
  
  .strength-meter {
    height: 4.5px;
    background-color: #e9ecef;
    border-radius: 2.7px;
    margin-bottom: 4.5px;
  }
  
  .strength-bar {
    height: 100%;
    border-radius: 2.7px;
    transition: width 0.3s ease-in-out;
  }
  
  .strength-text {
    font-size: var(--fs-xs);
    font-weight: 500;
  }
  
  .password-match {
    margin-top: 9px;
    font-size: var(--fs-xs);
  }
  
  .auth-alert.success {
    background-color: rgba(40, 167, 69, 0.09);
    color: var(--success-color);
    border: 0.9px solid rgba(40, 167, 69, 0.18);
  }
  
  .sign-btn.router-link-active {
    display: inline-block;
    text-align: center;
    text-decoration: none;
  }
  </style>