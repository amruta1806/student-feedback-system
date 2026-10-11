// Jenkins pipeline for the Student Feedback System.
// This version uses "bat" for a Jenkins server running on Windows.
// If Jenkins runs on Linux, replace every "bat" with "sh".

pipeline {
    agent any

    environment {
        AWS_DEFAULT_REGION = 'ap-southeast-2'
        LAMBDA_NAME        = 'FeedbackFunction'
        IMAGE_NAME         = 'student-feedback-form'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install') {
            steps {
                bat 'python -m pip install -r requirements.txt'
            }
        }

                 bat 'docker build -f Dockerfile.test -t feedback-tests .'
           bat 'docker run --rm feedback-tests'

        stage('Docker Build') {
            steps {
                bat 'docker build -t %IMAGE_NAME%:%BUILD_NUMBER% -t %IMAGE_NAME%:latest .'
            }
        }

        stage('Deploy Lambda') {
            steps {
                withCredentials([usernamePassword(
                        credentialsId: 'aws-credentials',
                        usernameVariable: 'AWS_ACCESS_KEY_ID',
                        passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
                    bat '''
                        powershell Compress-Archive -Path lambda_function.py -DestinationPath lambda.zip -Force
                        aws lambda update-function-code --function-name %LAMBDA_NAME% --zip-file fileb://lambda.zip --region %AWS_DEFAULT_REGION%
                    '''
                }
            }
        }

        stage('Run Container') {
            steps {
                bat '''
                    docker rm -f feedback-form || ver > nul
                    docker run -d --name feedback-form -p 8080:80 %IMAGE_NAME%:latest
                '''
            }
        }
    }

    post {
        success { echo 'Pipeline succeeded: tests passed, Lambda deployed, container running on port 8080.' }
        failure { echo 'Pipeline failed. Check the stage logs.' }
    }
}
