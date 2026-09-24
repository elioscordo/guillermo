import numpy as np


class KalmanHedgeEstimator:
    """
    Online recursive Kalman Filter to estimate dynamic hedge ratio and spread.
    
    State vector: theta_t = [alpha_t, beta_t]^T
    Observation:  y_t = [1, x_t] * theta_t + v_t,  v_t ~ N(0, R)
    Transition:   theta_t = theta_{t-1} + w_t,     w_t ~ N(0, Q)
    """

    def __init__(self, delta: float = 1e-4, r_variance: float = 1e-3) -> None:
        # delta governs parameter drift variance in Q
        self.delta = delta
        self.R = r_variance

        # State vector: [intercept, hedge_ratio]
        self.theta = np.zeros(2)

        # State covariance matrix P initialized with high uncertainty
        self.P = np.eye(2) * 1.0

        # Process noise covariance matrix Q
        self.Q = (self.delta / (1.0 - self.delta)) * np.eye(2)

        self.initialized = False

    def update(self, y: float, x: float) -> tuple[float, float, float]:
        """
        Ingest observation (y, x), perform Kalman step, and return (error, beta, alpha).
        """
        # Observation vector H_t = [1.0, x]
        H = np.array([1.0, x])

        if not self.initialized:
            # Cold start: set initial beta using direct price ratio
            self.theta = np.array([0.0, y / x if x != 0.0 else 1.0])
            self.initialized = True

        # 1. State prediction: theta_{t|t-1} = theta_{t-1} (Random Walk)
        # 2. Covariance prediction: P_{t|t-1} = P_{t-1} + Q
        P_pred = self.P + self.Q

        # 3. Measurement prediction error (Spread innovation): e_t = y_t - H * theta
        y_hat = np.dot(H, self.theta)
        error = y - y_hat

        # 4. Innovation covariance: S_t = H * P_pred * H^T + R
        S = np.dot(H, np.dot(P_pred, H)) + self.R

        # 5. Kalman gain: K_t = P_pred * H^T / S_t
        K = np.dot(P_pred, H) / S

        # 6. State update: theta_t = theta_{t-1} + K_t * error
        self.theta += K * error

        # 7. Covariance update: P_t = (I - K_t * H) * P_pred
        self.P = P_pred - np.outer(K, np.dot(H, P_pred))

        alpha = self.theta[0]
        beta = self.theta[1]

        return error, beta, alpha


from typing import Callable, Literal
import numpy as np


class UniversalRobustEstimator:
    """
    Unified Adaptive State Estimator for Cross-Asset StatArb.
    
    Supports:
      - Log-space transform (elasticity tracking)
      - Unscented Non-Linear transform (UKF)
      - Robust outlier dampening (Huber M-estimation or Student's-t reweighting)
    """

    def __init__(
        self,
        use_log: bool = True,
        use_nonlinear: bool = False,
        loss_type: Literal["gaussian", "huber", "student_t"] = "huber",
        huber_k: float = 1.5,          # Huber cutoff in std deviations
        student_dof: float = 4.0,       # Student-t degrees of freedom (nu)
        delta_noise: float = 1e-4,      # State drift rate (Q scaling)
        r_variance: float = 1e-3,       # Nominal measurement variance
        measurement_fn: Callable[[np.ndarray, float], float] | None = None,
    ) -> None:
        self.use_log = use_log
        self.use_nonlinear = use_nonlinear
        self.loss_type = loss_type
        self.huber_k = huber_k
        self.nu = student_dof
        self.delta = delta_noise
        self.R_base = r_variance

        # Measurement function h(theta, x). Default is linear: alpha + beta * x
        if measurement_fn is not None:
            self.h_fn = measurement_fn
        else:
            self.h_fn = lambda theta, x: theta[0] + theta[1] * x

        # State vector: [alpha, beta]
        self.dim_x = 2
        self.theta = np.array([0.0, 1.0])
        self.P = np.eye(self.dim_x) * 1.0
        self.Q = (self.delta / (1.0 - self.delta)) * np.eye(self.dim_x)

        # UKF Parameters (Van der Merwe scaled sigma points)
        self.alpha_ukf = 1e-3
        self.beta_ukf = 2.0  # Optimal for Gaussian prior
        self.kappa_ukf = 0.0
        self._init_ukf_weights()

        self.initialized = False

    def _init_ukf_weights(self) -> None:
        """Precompute Sigma Point weights for the Unscented Transform."""
        n = self.dim_x
        lambda_ = (self.alpha_ukf ** 2) * (n + self.kappa_ukf) - n
        self.lambda_ = lambda_

        num_sigmas = 2 * n + 1
        self.Wm = np.zeros(num_sigmas)
        self.Wc = np.zeros(num_sigmas)

        self.Wm[0] = lambda_ / (n + lambda_)
        self.Wc[0] = self.Wm[0] + (1.0 - self.alpha_ukf ** 2 + self.beta_ukf)

        for i in range(1, num_sigmas):
            weight = 1.0 / (2.0 * (n + lambda_))
            self.Wm[i] = weight
            self.Wc[i] = weight

        self.gamma_ukf = np.sqrt(n + lambda_)

    def _generate_sigma_points(self, mean: np.ndarray, cov: np.ndarray) -> np.ndarray:
        """Generate 2n + 1 deterministic sigma points around the current state mean."""
        n = self.dim_x
        sigmas = np.zeros((2 * n + 1, n))
        sigmas[0] = mean

        # Cholesky decomposition of cov: L * L.T = P
        try:
            L = np.linalg.cholesky(cov) * self.gamma_ukf
        except np.linalg.LinAlgError:
            # Fallback if covariance matrix loses positive-definiteness
            L = np.linalg.cholesky(cov + np.eye(n) * 1e-6) * self.gamma_ukf

        for i in range(n):
            sigmas[i + 1] = mean + L[:, i]
            sigmas[n + i + 1] = mean - L[:, i]

        return sigmas

    def _apply_robust_weighting(self, error: float, S: float) -> tuple[float, float]:
        """
        Calculates adjusted error or dynamic variance expansion using M-estimation.
        """
        std_innov = np.sqrt(S) if S > 0 else 1e-6
        norm_err = error / std_innov

        if self.loss_type == "huber":
            # Winsorize / clamp extreme errors outside k standard deviations
            if abs(norm_err) <= self.huber_k:
                effective_error = error
                effective_S = S
            else:
                # Downweight by truncating gradient
                effective_error = np.sign(error) * self.huber_k * std_innov
                effective_S = S
            return effective_error, effective_S

        elif self.loss_type == "student_t":
            # Scale observation variance based on Student-t posterior weight
            # w = (nu + 1) / (nu + norm_err^2)
            # R_dynamic = R / w
            weight = (self.nu + 1.0) / (self.nu + norm_err ** 2)
            dynamic_S = S / max(weight, 1e-4)
            return error, dynamic_S

        # Default Gaussian (identity)
        return error, S

    def update(self, y_raw: float, x_raw: float) -> tuple[float, float, float]:
        """
        Step recursive filter with incoming tick/bar observations.
        
        Returns:
            error: Stationary spread innovation (in log or linear space)
            beta:  Estimated hedge sensitivity parameter
            alpha: Estimated intercept
        """
        # 1. Coordinate Space Mapping
        y = np.log(y_raw) if self.use_log else y_raw
        x = np.log(x_raw) if self.use_log else x_raw

        if not self.initialized:
            # Cold-start baseline
            self.theta = np.array([0.0, y / x if x != 0 else 1.0])
            self.initialized = True

        # =====================================================================
        # PATH A: Linear Kalman Update
        # =====================================================================
        if not self.use_nonlinear:
            # Time update
            P_pred = self.P + self.Q
            H = np.array([1.0, x])

            # Innovation
            y_hat = np.dot(H, self.theta)
            raw_error = y - y_hat
            nominal_S = np.dot(H, np.dot(P_pred, H)) + self.R_base

            # Robust dampening step
            effective_error, effective_S = self._apply_robust_weighting(raw_error, nominal_S)

            # Gain calculation & state update
            K = np.dot(P_pred, H) / effective_S
            self.theta += K * effective_error
            self.P = P_pred - np.outer(K, np.dot(H, P_pred))

            return float(raw_error), float(self.theta[1]), float(self.theta[0])

        # =====================================================================
        # PATH B: Unscented Non-Linear Update (UKF)
        # =====================================================================
        else:
            # 1. Predict state and covariance
            theta_pred = self.theta.copy()
            P_pred = self.P + self.Q

            # 2. Generate Sigma Points
            sigmas = self._generate_sigma_points(theta_pred, P_pred)

            # 3. Propagate points through arbitrary measurement function h(theta, x)
            y_sigmas = np.array([self.h_fn(sigmas[i], x) for i in range(len(sigmas))])

            # 4. Predicted measurement mean and covariance
            y_hat = np.dot(self.Wm, y_sigmas)
            raw_error = y - y_hat

            # Innovation covariance P_yy
            y_diff = y_sigmas - y_hat
            P_yy = np.sum(self.Wc * (y_diff ** 2)) + self.R_base

            # Cross-covariance P_xy
            theta_diff = sigmas - theta_pred
            P_xy = np.sum(self.Wc[:, None] * theta_diff * y_diff[:, None], axis=0)

            # Robust dampening step
            effective_error, effective_S = self._apply_robust_weighting(raw_error, P_yy)

            # 5. Unscented Kalman Gain
            K = P_xy / effective_S

            # 6. State & Covariance Update
            self.theta = theta_pred + K * effective_error
            self.P = P_pred - np.outer(K, K) * effective_S

            return float(raw_error), float(self.theta[1]), float(self.theta[0])