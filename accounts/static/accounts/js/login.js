document.addEventListener("DOMContentLoaded", function () {

    const togglePassword = document.querySelector("#togglePassword");
    const password = document.querySelector("#id_password");
    const eyeIcon = document.querySelector("#eyeIcon");


    /* ============================================================
       MOSTRAR / OCULTAR SENHA
    ============================================================ */

    if (togglePassword && password && eyeIcon) {

        togglePassword.addEventListener("click", function () {

            const isPassword =
                password.getAttribute("type") === "password";


            if (isPassword) {

                password.setAttribute("type", "text");

                eyeIcon.classList.remove("bi-eye");
                eyeIcon.classList.add("bi-eye-slash");

                togglePassword.setAttribute(
                    "aria-label",
                    "Ocultar senha"
                );

                togglePassword.setAttribute(
                    "title",
                    "Ocultar senha"
                );

            } else {

                password.setAttribute("type", "password");

                eyeIcon.classList.remove("bi-eye-slash");
                eyeIcon.classList.add("bi-eye");

                togglePassword.setAttribute(
                    "aria-label",
                    "Mostrar senha"
                );

                togglePassword.setAttribute(
                    "title",
                    "Mostrar senha"
                );
            }

        });

    }

});