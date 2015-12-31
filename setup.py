from setuptools import setup

with open('requirements.txt') as f:
    requirements = f.readlines()

setup(name='pixiv-downloader',
      version='0.1',
      packages=['pixiv'],
      author='kzm4269',
      author_email='4269kzm@gmail.com',
      url='https://github.com/kzm4269/pixiv-downloader',
      install_requires=requirements,
      )
